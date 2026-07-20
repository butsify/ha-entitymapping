"""Config Flow and Options Flow for UI Entity Mapper.

Each config entry represents one mapping.
- ConfigFlow  : 2-step form to create a new mapping.
- OptionsFlow : 2-step form to edit an existing mapping.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ALL_SOURCE_DOMAINS,
    ALL_TARGET_DOMAINS,
    DOMAIN,
    Direction,
    MappingMode,
    MODE_VALID_SOURCE_DOMAINS,
    MODE_VALID_TARGET_DOMAINS,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _get_entity_domain(entity_id: str) -> str:
    """Extract the domain part of an entity_id."""
    return entity_id.split(".")[0] if "." in entity_id else ""


def _get_valid_modes(source_domain: str, target_domain: str) -> list[str]:
    """Return mapping modes that are valid for the given source/target domains."""
    return [
        mode
        for mode in MappingMode
        if source_domain in MODE_VALID_SOURCE_DOMAINS.get(mode, [])
        and target_domain in MODE_VALID_TARGET_DOMAINS.get(mode, [])
    ]


def _validate_mode_compat(
    source_domain: str, target_domain: str, mode: str
) -> str | None:
    """Return an error key if the combo is invalid, else None."""
    if source_domain not in MODE_VALID_SOURCE_DOMAINS.get(mode, []):
        return "invalid_source_for_mode"
    if target_domain not in MODE_VALID_TARGET_DOMAINS.get(mode, []):
        return "invalid_target_for_mode"
    return None


def _base_mapping_schema(defaults: dict[str, Any], mode_options: list | None = None) -> vol.Schema:
    """Build the voluptuous schema for step 1 (base mapping settings + mode)."""
    if mode_options is None:
        mode_options = [
            selector.SelectOptionDict(value=m, label=m.replace("_", " ").title())
            for m in MappingMode
        ]
    return vol.Schema(
        {
            vol.Required(
                "name", default=defaults.get("name", "")
            ): selector.TextSelector(),
            vol.Required(
                "source_entity", default=defaults.get("source_entity", "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=ALL_SOURCE_DOMAINS)
            ),
            vol.Required(
                "target_entity", default=defaults.get("target_entity", "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=ALL_TARGET_DOMAINS)
            ),
            vol.Required(
                "direction",
                default=defaults.get("direction", Direction.UNIDIRECTIONAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=Direction.UNIDIRECTIONAL,
                            label="Unidirectional (source -> target)",
                        ),
                        selector.SelectOptionDict(
                            value=Direction.BIDIRECTIONAL,
                            label="Bidirectional (source <-> target)",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                "enabled", default=defaults.get("enabled", True)
            ): selector.BooleanSelector(),
            vol.Required(
                "prevent_loop", default=defaults.get("prevent_loop", True)
            ): selector.BooleanSelector(),
            vol.Required(
                "retry_delay_seconds",
                default=defaults.get("retry_delay_seconds", 0),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3600, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                "max_retries",
                default=defaults.get("max_retries", 1),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=20, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                "mode", default=defaults.get("mode", MappingMode.BOOLEAN_MIRROR)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=mode_options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _transform_schema_for_mode(mode: str, defaults: dict[str, Any]) -> vol.Schema | None:
    """Return the transform schema for a given mode, or None if no transform is needed."""
    ns = selector.NumberSelectorConfig(
        min=-999999, max=999999, step=0.1, mode=selector.NumberSelectorMode.BOX
    )
    if mode == MappingMode.NUMERIC_PASSTHROUGH:
        return None
    if mode == MappingMode.BOOLEAN_MIRROR:
        return vol.Schema(
            {
                vol.Optional("invert", default=defaults.get("invert", False)): selector.BooleanSelector(),
            }
        )
    if mode == MappingMode.NUMERIC_THRESHOLD:
        return vol.Schema(
            {
                vol.Required("threshold", default=defaults.get("threshold", 50.0)): selector.NumberSelector(ns),
            }
        )
    if mode == MappingMode.NUMERIC_SCALED:
        return vol.Schema(
            {
                vol.Required("input_min", default=defaults.get("input_min", 0.0)): selector.NumberSelector(ns),
                vol.Required("input_max", default=defaults.get("input_max", 100.0)): selector.NumberSelector(ns),
                vol.Required("output_min", default=defaults.get("output_min", 0.0)): selector.NumberSelector(ns),
                vol.Required("output_max", default=defaults.get("output_max", 100.0)): selector.NumberSelector(ns),
                vol.Optional("invert", default=defaults.get("invert", False)): selector.BooleanSelector(),
                vol.Optional("round", default=defaults.get("round", False)): selector.BooleanSelector(),
            }
        )
    if mode == MappingMode.LIGHT_MIRROR:
        return vol.Schema(
            {
                vol.Optional("mirror_brightness", default=defaults.get("mirror_brightness", True)): selector.BooleanSelector(),
                vol.Optional("mirror_color_temp", default=defaults.get("mirror_color_temp", False)): selector.BooleanSelector(),
            }
        )
    return None


def _extract_transform(mode: str, user_input: dict[str, Any]) -> dict[str, Any]:
    """Extract only the relevant transform fields for the given mode."""
    if mode == MappingMode.BOOLEAN_MIRROR:
        return {"invert": bool(user_input.get("invert", False))}
    if mode == MappingMode.NUMERIC_PASSTHROUGH:
        return {}
    if mode == MappingMode.NUMERIC_THRESHOLD:
        return {"threshold": float(user_input.get("threshold", 50.0))}
    if mode == MappingMode.NUMERIC_SCALED:
        return {
            "input_min": float(user_input.get("input_min", 0.0)),
            "input_max": float(user_input.get("input_max", 100.0)),
            "output_min": float(user_input.get("output_min", 0.0)),
            "output_max": float(user_input.get("output_max", 100.0)),
            "invert": bool(user_input.get("invert", False)),
            "round": bool(user_input.get("round", False)),
        }
    if mode == MappingMode.LIGHT_MIRROR:
        return {
            "mirror_brightness": bool(user_input.get("mirror_brightness", True)),
            "mirror_color_temp": bool(user_input.get("mirror_color_temp", False)),
        }
    return {}



# ---------------------------------------------------------------------------
# Config Flow (one-shot entry creation)
# ---------------------------------------------------------------------------


class UiEntityMapperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle creation of a new mapping config entry (one entry per mapping)."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._form_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "UiEntityMapperOptionsFlow":
        """Return the options flow handler."""
        return UiEntityMapperOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 1: collect base mapping settings + mode."""
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = {}
        mode_options = None  # None = show all modes

        if user_input is not None:
            source_domain = _get_entity_domain(user_input.get("source_entity", ""))
            target_domain = _get_entity_domain(user_input.get("target_entity", ""))
            mode = user_input.get("mode", "")
            err = _validate_mode_compat(source_domain, target_domain, mode)
            if err:
                errors["mode"] = err
                defaults = dict(user_input)
                valid_modes = _get_valid_modes(source_domain, target_domain)
                if valid_modes:
                    mode_options = [
                        selector.SelectOptionDict(value=m, label=m.replace("_", " ").title())
                        for m in valid_modes
                    ]
            else:
                self._form_data = {
                    "id": str(uuid.uuid4()),
                    "name": user_input["name"],
                    "source_entity": user_input["source_entity"],
                    "target_entity": user_input["target_entity"],
                    "direction": user_input.get("direction", Direction.UNIDIRECTIONAL),
                    "enabled": bool(user_input.get("enabled", True)),
                    "prevent_loop": bool(user_input.get("prevent_loop", True)),
                    "retry_delay_seconds": float(user_input.get("retry_delay_seconds", 0)),
                    "max_retries": int(user_input.get("max_retries", 1)),
                    "mode": mode,
                    "debounce_ms": 0,
                    "throttle_ms": 0,
                }
                if mode == MappingMode.NUMERIC_PASSTHROUGH:
                    full_config = {**self._form_data, "transform": {}}
                    return self.async_create_entry(title=full_config["name"], data=full_config)
                return await self.async_step_transform()

        return self.async_show_form(
            step_id="user",
            data_schema=_base_mapping_schema(defaults, mode_options),
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2 (legacy, no longer used — kept for in-flight flows)."""
        return await self.async_step_transform()

    async def async_step_transform(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: configure mode-specific transform parameters."""
        mode = self._form_data.get("mode", MappingMode.BOOLEAN_MIRROR)
        schema = _transform_schema_for_mode(mode, {})

        if user_input is not None:
            full_config = {**self._form_data, "transform": _extract_transform(mode, user_input)}
            return self.async_create_entry(title=full_config["name"], data=full_config)

        return self.async_show_form(
            step_id="transform",
            data_schema=schema,
            description_placeholders={"mode_label": mode.replace("_", " ").title()},
        )

    async def async_step_import(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a mapping entry from imported data (import_mappings service)."""
        if "id" not in user_input:
            user_input = {**user_input, "id": str(uuid.uuid4())}
        return self.async_create_entry(
            title=user_input.get("name", "Imported Mapping"), data=user_input
        )


# ---------------------------------------------------------------------------
# Options Flow (edits an existing mapping entry)
# ---------------------------------------------------------------------------


class UiEntityMapperOptionsFlow(OptionsFlow):
    """Two-step options flow to edit a single mapping."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._form_data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 1: edit base mapping settings + mode (pre-filled from entry.data)."""
        defaults = dict(self._entry.data)
        errors: dict[str, str] = {}

        # Pre-filter modes based on the known source/target from entry data
        src = _get_entity_domain(defaults.get("source_entity", ""))
        tgt = _get_entity_domain(defaults.get("target_entity", ""))
        valid_for_current = _get_valid_modes(src, tgt)
        mode_options: list | None = [
            selector.SelectOptionDict(value=m, label=m.replace("_", " ").title())
            for m in valid_for_current
        ] if valid_for_current else None

        if user_input is not None:
            source_domain = _get_entity_domain(user_input.get("source_entity", ""))
            target_domain = _get_entity_domain(user_input.get("target_entity", ""))
            mode = user_input.get("mode", "")
            err = _validate_mode_compat(source_domain, target_domain, mode)
            if err:
                errors["mode"] = err
                defaults = dict(user_input)
                valid_modes = _get_valid_modes(source_domain, target_domain)
                mode_options = [
                    selector.SelectOptionDict(value=m, label=m.replace("_", " ").title())
                    for m in valid_modes
                ] if valid_modes else None
            else:
                self._form_data = {
                    "id": self._entry.data.get("id", str(uuid.uuid4())),
                    "name": user_input["name"],
                    "source_entity": user_input["source_entity"],
                    "target_entity": user_input["target_entity"],
                    "direction": user_input.get("direction", Direction.UNIDIRECTIONAL),
                    "enabled": bool(user_input.get("enabled", True)),
                    "prevent_loop": bool(user_input.get("prevent_loop", True)),
                    "retry_delay_seconds": float(user_input.get("retry_delay_seconds", 0)),
                    "max_retries": int(user_input.get("max_retries", 1)),
                    "mode": mode,
                    "debounce_ms": 0,
                    "throttle_ms": 0,
                }
                if mode == MappingMode.NUMERIC_PASSTHROUGH:
                    new_config = {**self._form_data, "transform": {}}
                    self.hass.config_entries.async_update_entry(
                        self._entry, title=new_config["name"], data=new_config
                    )
                    return self.async_create_entry(title=new_config["name"], data={"_v": int(time.time())})
                return await self.async_step_transform()

        return self.async_show_form(
            step_id="init",
            data_schema=_base_mapping_schema(defaults, mode_options),
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2 (legacy, no longer used — kept for in-flight flows)."""
        return await self.async_step_transform()

    async def async_step_transform(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: handle transform form submission."""
        mode = self._form_data.get("mode", MappingMode.BOOLEAN_MIRROR)
        existing_transform = self._entry.data.get("transform", {})
        schema = _transform_schema_for_mode(mode, existing_transform)

        if user_input is not None:
            new_config = {**self._form_data, "transform": _extract_transform(mode, user_input)}
            self.hass.config_entries.async_update_entry(
                self._entry, title=new_config["name"], data=new_config
            )
            return self.async_create_entry(title=new_config["name"], data={"_v": int(time.time())})

        return self.async_show_form(
            step_id="transform",
            data_schema=schema,
            description_placeholders={"mode_label": mode.replace("_", " ").title()},
        )


