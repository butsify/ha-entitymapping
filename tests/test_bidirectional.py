"""Tests for bidirectional loop prevention in MappingManager."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ui_entity_mapper.const import LOOP_GUARD_WINDOW, Direction, MappingMode
from custom_components.ui_entity_mapper.manager import MappingManager
from custom_components.ui_entity_mapper.storage import MappingConfig
from tests.conftest import MockHass, make_state


def _make_bidir_mapping(prevent_loop: bool = True) -> MappingConfig:
    return {
        "id": "bidir-id",
        "name": "Bidirectional",
        "enabled": True,
        "direction": Direction.BIDIRECTIONAL,
        "source_entity": "switch.a",
        "target_entity": "switch.b",
        "mode": MappingMode.BOOLEAN_MIRROR,
        "retry_delay_seconds": 0,
        "max_retries": 0,
        "prevent_loop": prevent_loop,
        "debounce_ms": 0,
        "throttle_ms": 0,
        "transform": {},
    }


def _make_manager(hass: MockHass, mapping: MappingConfig) -> MappingManager:
    storage = MagicMock()
    storage.get_mappings.return_value = [mapping]
    storage.get_mapping.return_value = mapping
    storage.async_load = AsyncMock()
    return MappingManager(hass, storage, "test-entry")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Forward propagation A → B suppresses the B echo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_sets_loop_guard_on_target():
    """After A → B propagation, _loop_guard[switch.b] should be fresh."""
    hass = MockHass()
    hass.set_state("switch.b", "off")

    mapping = _make_bidir_mapping()
    manager = _make_manager(hass, mapping)

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        await manager._do_process_mapping(
            mapping, make_state("switch.a", "on"), reverse=False, force=True
        )

    assert "switch.b" in manager._loop_guard
    age = time.monotonic() - manager._loop_guard["switch.b"]
    assert age < LOOP_GUARD_WINDOW, "Loop guard on target should be fresh"


@pytest.mark.asyncio
async def test_forward_echo_suppressed():
    """If switch.b just got written by us, a reverse event for it should be suppressed."""
    hass = MockHass()
    hass.set_state("switch.b", "off")

    mapping = _make_bidir_mapping()
    manager = _make_manager(hass, mapping)

    # Simulate that we just wrote to switch.b
    manager._loop_guard["switch.b"] = time.monotonic()

    service_calls: list = []
    hass.services.calls = service_calls

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        await manager._do_process_mapping(
            mapping, make_state("switch.b", "on"), reverse=True, force=False
        )

    # The loop guard should have blocked execution — no service call
    assert len(hass.services.calls) == 0, "Echo should be suppressed by loop guard"


# ---------------------------------------------------------------------------
# Reverse propagation B → A suppresses the A echo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reverse_sets_loop_guard_on_source():
    """After B → A propagation, _loop_guard[switch.a] should be fresh."""
    hass = MockHass()
    hass.set_state("switch.a", "off")

    mapping = _make_bidir_mapping()
    manager = _make_manager(hass, mapping)

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        await manager._do_process_mapping(
            mapping, make_state("switch.b", "on"), reverse=True, force=True
        )

    assert "switch.a" in manager._loop_guard
    age = time.monotonic() - manager._loop_guard["switch.a"]
    assert age < LOOP_GUARD_WINDOW


@pytest.mark.asyncio
async def test_source_echo_suppressed_after_reverse():
    """After B→A write, an A change event should be suppressed (prevent ping-pong)."""
    hass = MockHass()
    mapping = _make_bidir_mapping()
    manager = _make_manager(hass, mapping)

    # Simulate that we just wrote to switch.a (from a reverse process)
    manager._loop_guard["switch.a"] = time.monotonic()

    service_calls: list = []
    hass.services.calls = service_calls

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        # This would be A→B forward, but A was just written by us
        await manager._do_process_mapping(
            mapping, make_state("switch.a", "on"), reverse=False, force=False
        )

    assert len(hass.services.calls) == 0, "Source echo should be suppressed"


# ---------------------------------------------------------------------------
# No suppression when loop guard is stale (> LOOP_GUARD_WINDOW)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_loop_guard_does_not_suppress():
    """A guard older than LOOP_GUARD_WINDOW should NOT suppress a real user change."""
    hass = MockHass()
    hass.set_state("switch.b", "off")

    mapping = _make_bidir_mapping()
    manager = _make_manager(hass, mapping)

    # Set a stale guard (far in the past)
    manager._loop_guard["switch.b"] = time.monotonic() - (LOOP_GUARD_WINDOW + 10)

    service_calls_before = len(hass.services.calls)

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        await manager._do_process_mapping(
            mapping, make_state("switch.b", "on"), reverse=True, force=False
        )

    # Should have made a service call (writing to switch.a)
    assert len(hass.services.calls) > service_calls_before


# ---------------------------------------------------------------------------
# prevent_loop=False: guard is not applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prevent_loop_false_allows_echo():
    """When prevent_loop is False, the loop guard should never suppress."""
    hass = MockHass()
    hass.set_state("switch.b", "off")

    mapping = _make_bidir_mapping(prevent_loop=False)
    manager = _make_manager(hass, mapping)

    # Set a fresh guard
    manager._loop_guard["switch.b"] = time.monotonic()

    with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
        await manager._do_process_mapping(
            mapping, make_state("switch.b", "on"), reverse=True, force=False
        )

    # Even with a fresh guard, since prevent_loop=False, the call should proceed
    assert len(hass.services.calls) > 0
