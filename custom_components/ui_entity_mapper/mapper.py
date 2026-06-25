"""Pure mapping logic for UI Entity Mapper.

This module is intentionally free of HA service calls — it only *computes*
what service call should be made, keeping business logic easy to unit-test.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN

from .const import MappingMode
from .storage import TransformConfig

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

# (domain, service, data) tuple describing an HA service call
ServiceCall = tuple[str, str, dict[str, Any]]

# Acceptable delta for numeric target verification (absolute units)
NUMERIC_TOLERANCE: float = 1.0


# ---------------------------------------------------------------------------
# Value scaling helper
# ---------------------------------------------------------------------------


def scale_value(
    val: float,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
    *,
    invert: bool = False,
    clamp: bool = True,
    do_round: bool = False,
) -> float:
    """Linearly map *val* from [in_min, in_max] to [out_min, out_max].

    Supports inversion, clamping, and integer rounding.
    """
    if in_max == in_min:
        return out_min
    ratio = (val - in_min) / (in_max - in_min)
    if invert:
        ratio = 1.0 - ratio
    result = out_min + ratio * (out_max - out_min)
    if clamp:
        lo = min(out_min, out_max)
        hi = max(out_min, out_max)
        result = max(lo, min(hi, result))
    if do_round:
        result = float(round(result))
    return result


# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------


def compute_service_call(
    mode: str,
    source_state: str,
    source_entity_id: str,
    target_entity_id: str,
    transform: TransformConfig,
) -> ServiceCall | None:
    """Return the HA service call tuple for the given mode and source state.

    Returns None if the state cannot be mapped (e.g., non-numeric string for
    a numeric mode).
    """
    target_domain = target_entity_id.split(".")[0]

    if mode == MappingMode.BOOLEAN_MIRROR:
        return _boolean_mirror(source_state, target_domain, target_entity_id, transform)

    if mode == MappingMode.NUMERIC_PASSTHROUGH:
        return _numeric_passthrough(source_state, target_entity_id)

    if mode == MappingMode.NUMERIC_SCALED:
        return _numeric_scaled(source_state, target_domain, target_entity_id, transform)

    if mode == MappingMode.NUMERIC_THRESHOLD:
        return _numeric_threshold(source_state, target_domain, target_entity_id, transform)

    if mode == MappingMode.LIGHT_MIRROR:
        # Simple on/off without attribute context — full version handled by
        # compute_light_mirror_call() when the full State object is available.
        is_on = source_state == "on"
        service = "turn_on" if is_on else "turn_off"
        return ("light", service, {"entity_id": target_entity_id})

    _LOGGER.warning("Unknown mapping mode: %s", mode)
    return None


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _boolean_mirror(
    source_state: str, target_domain: str, target_entity_id: str, transform: TransformConfig
) -> ServiceCall | None:
    """Map source ON/OFF to target turn_on/turn_off."""
    is_on = source_state == "on"
    if transform.get("invert", False):
        is_on = not is_on
    service = "turn_on" if is_on else "turn_off"
    if target_domain in ("switch", "light"):
        return (target_domain, service, {"entity_id": target_entity_id})
    return None


def _numeric_passthrough(
    source_state: str, target_entity_id: str
) -> ServiceCall | None:
    """Parse numeric state and forward directly to number.set_value."""
    try:
        value = float(source_state)
    except (ValueError, TypeError):
        _LOGGER.debug("Cannot parse numeric state: %r", source_state)
        return None
    return ("number", "set_value", {"entity_id": target_entity_id, "value": value})


def _numeric_scaled(
    source_state: str,
    target_domain: str,
    target_entity_id: str,
    transform: TransformConfig,
) -> ServiceCall | None:
    """Scale a numeric source value to the target range."""
    try:
        val = float(source_state)
    except (ValueError, TypeError):
        _LOGGER.debug("Cannot parse numeric state for scaling: %r", source_state)
        return None

    scaled = scale_value(
        val,
        float(transform.get("input_min", 0)),
        float(transform.get("input_max", 100)),
        float(transform.get("output_min", 0)),
        float(transform.get("output_max", 100)),
        invert=bool(transform.get("invert", False)),
        clamp=True,
        do_round=bool(transform.get("round", False)),
    )

    if target_domain == "number":
        return ("number", "set_value", {"entity_id": target_entity_id, "value": scaled})
    if target_domain == "light":
        return (
            "light",
            "turn_on",
            {"entity_id": target_entity_id, ATTR_BRIGHTNESS: int(round(scaled))},
        )
    return None


def _numeric_threshold(
    source_state: str,
    target_domain: str,
    target_entity_id: str,
    transform: TransformConfig,
) -> ServiceCall | None:
    """Turn target on when source >= threshold, off otherwise."""
    try:
        val = float(source_state)
    except (ValueError, TypeError):
        _LOGGER.debug("Cannot parse numeric state for threshold: %r", source_state)
        return None

    threshold = float(transform.get("threshold", 50))
    is_on = val >= threshold
    service = "turn_on" if is_on else "turn_off"

    if target_domain in ("switch", "light"):
        return (target_domain, service, {"entity_id": target_entity_id})
    return None


# ---------------------------------------------------------------------------
# Light mirror (uses full State object for attribute access)
# ---------------------------------------------------------------------------


def compute_light_mirror_call(
    source_state_obj: "State",
    target_entity_id: str,
    transform: TransformConfig,
) -> ServiceCall | None:
    """Compute a light-mirror service call using the full HA State object.

    Mirrors on/off and, optionally, brightness and colour temperature.
    """
    if source_state_obj is None:
        return None
    if source_state_obj.state not in ("on", "off"):
        return None
    if source_state_obj.state == "off":
        return ("light", "turn_off", {"entity_id": target_entity_id})

    data: dict[str, Any] = {"entity_id": target_entity_id}
    attrs = source_state_obj.attributes

    if transform.get("mirror_brightness", True):
        brightness = attrs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            data[ATTR_BRIGHTNESS] = int(brightness)

    if transform.get("mirror_color_temp", False):
        color_temp = attrs.get(ATTR_COLOR_TEMP_KELVIN)
        if color_temp is not None:
            data[ATTR_COLOR_TEMP_KELVIN] = int(color_temp)

    return ("light", "turn_on", data)


# ---------------------------------------------------------------------------
# Target-reached verification helpers
# ---------------------------------------------------------------------------


def check_boolean_target_reached(
    hass: "HomeAssistant", entity_id: str, expected_on: bool
) -> bool:
    """Return True if the target entity currently matches the expected on/off state."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return False
    return (state.state == "on") == expected_on


def check_numeric_target_reached(
    hass: "HomeAssistant",
    entity_id: str,
    expected: float,
    tolerance: float = NUMERIC_TOLERANCE,
) -> bool:
    """Return True if the target numeric entity is within *tolerance* of *expected*."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return False
    try:
        current = float(state.state)
    except (ValueError, TypeError):
        return False
    return abs(current - expected) <= tolerance
