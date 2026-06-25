"""Tests for numeric_threshold mapping mode."""
from __future__ import annotations

import pytest

from custom_components.ui_entity_mapper.const import MappingMode
from custom_components.ui_entity_mapper.mapper import compute_service_call


@pytest.mark.parametrize(
    ("source_state", "threshold", "expected_service"),
    [
        ("60", 50, "turn_on"),   # above threshold
        ("40", 50, "turn_off"),  # below threshold
        ("50", 50, "turn_on"),   # exactly at threshold → ON
        ("0", 50, "turn_off"),
        ("100", 50, "turn_on"),
    ],
)
def test_threshold_switch_target(source_state, threshold, expected_service):
    result = compute_service_call(
        MappingMode.NUMERIC_THRESHOLD,
        source_state,
        "sensor.temp",
        "switch.heater",
        {"threshold": threshold},
    )
    assert result == ("switch", expected_service, {"entity_id": "switch.heater"})


def test_threshold_light_target():
    result = compute_service_call(
        MappingMode.NUMERIC_THRESHOLD,
        "75",
        "sensor.lux",
        "light.lamp",
        {"threshold": 50},
    )
    assert result == ("light", "turn_on", {"entity_id": "light.lamp"})


def test_threshold_non_numeric_returns_none():
    result = compute_service_call(
        MappingMode.NUMERIC_THRESHOLD,
        "unknown",
        "sensor.temp",
        "switch.heater",
        {"threshold": 50},
    )
    assert result is None


def test_threshold_default_50():
    """When no threshold key is in transform, default 50 applies."""
    result = compute_service_call(
        MappingMode.NUMERIC_THRESHOLD,
        "51",
        "sensor.temp",
        "switch.heater",
        {},  # no threshold key
    )
    assert result is not None
    assert result[1] == "turn_on"
