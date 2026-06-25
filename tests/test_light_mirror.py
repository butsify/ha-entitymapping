"""Tests for light_mirror mapping mode."""
from __future__ import annotations

import pytest

from custom_components.ui_entity_mapper.mapper import compute_light_mirror_call
from tests.conftest import MockState


def _state(state: str, brightness: int | None = None, color_temp: int | None = None) -> MockState:
    attrs = {}
    if brightness is not None:
        attrs["brightness"] = brightness
    if color_temp is not None:
        attrs["color_temp_kelvin"] = color_temp
    return MockState("light.source", state, attrs)


def test_light_mirror_off():
    result = compute_light_mirror_call(_state("off"), "light.target", {})
    assert result == ("light", "turn_off", {"entity_id": "light.target"})


def test_light_mirror_on_no_brightness():
    """With no brightness in source attrs, turn_on with only entity_id."""
    result = compute_light_mirror_call(_state("on"), "light.target", {})
    assert result is not None
    assert result[1] == "turn_on"
    assert "brightness" not in result[2]


def test_light_mirror_brightness():
    result = compute_light_mirror_call(
        _state("on", brightness=128), "light.target", {"mirror_brightness": True}
    )
    assert result is not None
    assert result[2]["brightness"] == 128


def test_light_mirror_brightness_disabled():
    result = compute_light_mirror_call(
        _state("on", brightness=128), "light.target", {"mirror_brightness": False}
    )
    assert result is not None
    assert "brightness" not in result[2]


def test_light_mirror_color_temp():
    result = compute_light_mirror_call(
        _state("on", color_temp=4000),
        "light.target",
        {"mirror_brightness": False, "mirror_color_temp": True},
    )
    assert result is not None
    assert result[2]["color_temp_kelvin"] == 4000


def test_light_mirror_none_source_returns_none():
    result = compute_light_mirror_call(None, "light.target", {})  # type: ignore[arg-type]
    assert result is None


def test_light_mirror_unknown_state_returns_none():
    result = compute_light_mirror_call(_state("unknown"), "light.target", {})
    assert result is None
