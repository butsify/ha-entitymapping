"""Tests for numeric_scaled mapping mode and the scale_value helper."""
from __future__ import annotations

import pytest

from custom_components.ui_entity_mapper.const import MappingMode
from custom_components.ui_entity_mapper.mapper import compute_service_call, scale_value


# ---------------------------------------------------------------------------
# scale_value unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("val", "in_min", "in_max", "out_min", "out_max", "expected"),
    [
        (0, 0, 100, 0, 255, 0.0),
        (100, 0, 100, 0, 255, 255.0),
        (50, 0, 100, 0, 255, 127.5),
        (0, 0, 100, 100, 200, 100.0),
        (100, 0, 100, 100, 200, 200.0),
    ],
)
def test_scale_value_linear(val, in_min, in_max, out_min, out_max, expected):
    assert scale_value(val, in_min, in_max, out_min, out_max) == pytest.approx(expected)


def test_scale_value_clamp_high():
    result = scale_value(200, 0, 100, 0, 255, clamp=True)
    assert result == 255.0


def test_scale_value_clamp_low():
    result = scale_value(-50, 0, 100, 0, 255, clamp=True)
    assert result == 0.0


def test_scale_value_no_clamp():
    result = scale_value(200, 0, 100, 0, 255, clamp=False)
    assert result == pytest.approx(510.0)


def test_scale_value_invert():
    result = scale_value(0, 0, 100, 0, 255, invert=True)
    assert result == pytest.approx(255.0)
    result2 = scale_value(100, 0, 100, 0, 255, invert=True)
    assert result2 == pytest.approx(0.0)


def test_scale_value_round():
    result = scale_value(50, 0, 100, 0, 255, do_round=True)
    assert result == 128.0  # round(127.5) = 128


def test_scale_value_zero_range_returns_out_min():
    result = scale_value(50, 100, 100, 0, 255)
    assert result == 0.0


# ---------------------------------------------------------------------------
# compute_service_call — numeric_scaled
# ---------------------------------------------------------------------------


def test_scaled_number_target():
    result = compute_service_call(
        MappingMode.NUMERIC_SCALED,
        "50",
        "sensor.src",
        "number.tgt",
        {"input_min": 0, "input_max": 100, "output_min": 0, "output_max": 255},
    )
    assert result is not None
    domain, service, data = result
    assert domain == "number"
    assert service == "set_value"
    assert data["value"] == pytest.approx(127.5)


def test_scaled_light_brightness():
    result = compute_service_call(
        MappingMode.NUMERIC_SCALED,
        "100",
        "sensor.src",
        "light.tgt",
        {"input_min": 0, "input_max": 100, "output_min": 0, "output_max": 255},
    )
    assert result is not None
    domain, service, data = result
    assert domain == "light"
    assert service == "turn_on"
    assert data["brightness"] == 255


def test_scaled_non_numeric_returns_none():
    result = compute_service_call(
        MappingMode.NUMERIC_SCALED,
        "unavailable",
        "sensor.src",
        "number.tgt",
        {"input_min": 0, "input_max": 100, "output_min": 0, "output_max": 255},
    )
    assert result is None


def test_scaled_with_invert():
    result = compute_service_call(
        MappingMode.NUMERIC_SCALED,
        "100",
        "sensor.src",
        "number.tgt",
        {
            "input_min": 0,
            "input_max": 100,
            "output_min": 0,
            "output_max": 100,
            "invert": True,
        },
    )
    assert result is not None
    assert result[2]["value"] == pytest.approx(0.0)
