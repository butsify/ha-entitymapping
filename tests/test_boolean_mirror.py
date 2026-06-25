"""Tests for boolean_mirror mapping mode."""
from __future__ import annotations

import pytest

from custom_components.ui_entity_mapper.const import MappingMode
from custom_components.ui_entity_mapper.mapper import compute_service_call


@pytest.mark.parametrize(
    ("source_state", "target_entity", "expected"),
    [
        # switch target
        ("on", "switch.target", ("switch", "turn_on", {"entity_id": "switch.target"})),
        ("off", "switch.target", ("switch", "turn_off", {"entity_id": "switch.target"})),
        # light target
        ("on", "light.target", ("light", "turn_on", {"entity_id": "light.target"})),
        ("off", "light.target", ("light", "turn_off", {"entity_id": "light.target"})),
    ],
)
def test_boolean_mirror(source_state, target_entity, expected):
    result = compute_service_call(
        MappingMode.BOOLEAN_MIRROR,
        source_state,
        "binary_sensor.source",
        target_entity,
        {},
    )
    assert result == expected


def test_boolean_mirror_switch_source():
    """A switch as source should work identically to a binary_sensor."""
    result = compute_service_call(
        MappingMode.BOOLEAN_MIRROR,
        "on",
        "switch.source",
        "switch.target",
        {},
    )
    assert result == ("switch", "turn_on", {"entity_id": "switch.target"})


def test_boolean_mirror_unsupported_target_returns_none():
    """A number entity as target is not valid for boolean_mirror."""
    result = compute_service_call(
        MappingMode.BOOLEAN_MIRROR,
        "on",
        "binary_sensor.source",
        "number.target",
        {},
    )
    assert result is None
