"""Tests for domain/mode validation helpers in config_flow."""
from __future__ import annotations

import pytest

from custom_components.ui_entity_mapper.config_flow import (
    _get_valid_modes,
    _validate_mode_compat,
)
from custom_components.ui_entity_mapper.const import MappingMode


# ---------------------------------------------------------------------------
# _get_valid_modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_domain", "target_domain", "expected_modes"),
    [
        # binary_sensor → switch: only boolean_mirror
        ("binary_sensor", "switch", [MappingMode.BOOLEAN_MIRROR]),
        # switch → switch: only boolean_mirror
        ("switch", "switch", [MappingMode.BOOLEAN_MIRROR]),
        # light → light: boolean_mirror + light_mirror
        ("light", "light", [MappingMode.BOOLEAN_MIRROR, MappingMode.LIGHT_MIRROR]),
        # sensor → number: passthrough + scaled
        (
            "sensor",
            "number",
            [
                MappingMode.NUMERIC_PASSTHROUGH,
                MappingMode.NUMERIC_SCALED,
                MappingMode.NUMERIC_THRESHOLD,
            ],
        ),
        # sensor → switch: threshold only
        ("sensor", "switch", [MappingMode.NUMERIC_THRESHOLD]),
        # sensor → light: scaled + threshold
        ("sensor", "light", [MappingMode.NUMERIC_SCALED, MappingMode.NUMERIC_THRESHOLD]),
        # invalid combination
        ("binary_sensor", "number", []),
        ("sensor", "sensor", []),
    ],
)
def test_get_valid_modes(source_domain, target_domain, expected_modes):
    result = _get_valid_modes(source_domain, target_domain)
    assert set(result) == set(expected_modes), (
        f"source={source_domain} target={target_domain}: "
        f"expected {expected_modes}, got {result}"
    )


# ---------------------------------------------------------------------------
# _validate_mode_compat
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_domain", "target_domain", "mode", "expected_error"),
    [
        # valid combos → None
        ("binary_sensor", "switch", MappingMode.BOOLEAN_MIRROR, None),
        ("sensor", "number", MappingMode.NUMERIC_PASSTHROUGH, None),
        ("sensor", "number", MappingMode.NUMERIC_SCALED, None),
        ("sensor", "switch", MappingMode.NUMERIC_THRESHOLD, None),
        ("light", "light", MappingMode.LIGHT_MIRROR, None),
        # invalid source
        ("number", "switch", MappingMode.BOOLEAN_MIRROR, "invalid_source_for_mode"),
        ("binary_sensor", "number", MappingMode.NUMERIC_PASSTHROUGH, "invalid_source_for_mode"),
        # invalid target
        ("sensor", "sensor", MappingMode.NUMERIC_PASSTHROUGH, "invalid_target_for_mode"),
        ("binary_sensor", "number", MappingMode.BOOLEAN_MIRROR, "invalid_target_for_mode"),
    ],
)
def test_validate_mode_compat(source_domain, target_domain, mode, expected_error):
    result = _validate_mode_compat(source_domain, target_domain, mode)
    assert result == expected_error
