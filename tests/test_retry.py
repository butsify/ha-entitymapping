"""Tests for retry logic in MappingManager."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.ui_entity_mapper.const import MappingMode
from custom_components.ui_entity_mapper.manager import MappingManager, MappingStatus
from custom_components.ui_entity_mapper.storage import MappingConfig
from tests.conftest import MockHass, make_state


def _make_mapping(
    mapping_id: str = "test-id",
    retry_delay: float = 0,
    max_retries: int = 1,
    mode: str = MappingMode.BOOLEAN_MIRROR,
) -> MappingConfig:
    return {
        "id": mapping_id,
        "name": "Test",
        "enabled": True,
        "direction": "unidirectional",
        "source_entity": "binary_sensor.src",
        "target_entity": "switch.tgt",
        "mode": mode,
        "retry_delay_seconds": retry_delay,
        "max_retries": max_retries,
        "prevent_loop": False,  # Disable loop guard for unit tests
        "debounce_ms": 0,
        "throttle_ms": 0,
        "transform": {},
    }


def _make_manager(hass: MockHass) -> MappingManager:
    storage = MagicMock()
    storage.get_mappings.return_value = []
    storage.get_mapping.return_value = None
    storage.async_load = AsyncMock()
    manager = MappingManager(hass, storage, "test-entry")  # type: ignore[arg-type]
    return manager


# ---------------------------------------------------------------------------
# No retry when retry_delay_seconds == 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_retry_when_delay_zero():
    hass = MockHass()
    hass.set_state("switch.tgt", "on")  # target already on

    manager = _make_manager(hass)
    mapping = _make_mapping(retry_delay=0, max_retries=1)

    called_later: list[Any] = []

    with patch(
        "custom_components.ui_entity_mapper.manager.async_call_later",
        side_effect=lambda h, d, cb: called_later.append(d),
    ):
        with patch(
            "custom_components.ui_entity_mapper.manager.async_dispatcher_send"
        ):
            await manager._do_process_mapping(
                mapping, make_state("binary_sensor.src", "on"), reverse=False, force=True
            )

    assert called_later == [], "async_call_later should NOT be called when delay=0"


# ---------------------------------------------------------------------------
# No retry when max_retries == 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_retry_when_max_retries_zero():
    hass = MockHass()
    hass.set_state("switch.tgt", "off")  # target NOT reached → would retry if allowed

    manager = _make_manager(hass)
    mapping = _make_mapping(retry_delay=5, max_retries=0)

    called_later: list[Any] = []

    with patch(
        "custom_components.ui_entity_mapper.manager.async_call_later",
        side_effect=lambda h, d, cb: called_later.append(d),
    ):
        with patch(
            "custom_components.ui_entity_mapper.manager.async_dispatcher_send"
        ):
            await manager._do_process_mapping(
                mapping, make_state("binary_sensor.src", "on"), reverse=False, force=True
            )

    assert called_later == [], "async_call_later should NOT be called when max_retries=0"


# ---------------------------------------------------------------------------
# Retry IS scheduled when delay > 0 and target not reached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_scheduled_when_target_not_reached():
    hass = MockHass()
    hass.set_state("switch.tgt", "off")  # target NOT reached after command

    manager = _make_manager(hass)
    mapping = _make_mapping(retry_delay=3, max_retries=1)

    scheduled_delays: list[float] = []

    def fake_call_later(h, delay, cb):
        scheduled_delays.append(delay)
        return MagicMock()  # cancel handle

    with patch(
        "custom_components.ui_entity_mapper.manager.async_call_later",
        side_effect=fake_call_later,
    ):
        with patch(
            "custom_components.ui_entity_mapper.manager.async_dispatcher_send"
        ):
            await manager._do_process_mapping(
                mapping, make_state("binary_sensor.src", "on"), reverse=False, force=True
            )

    assert scheduled_delays == [3], "Expected one retry scheduled after 3 seconds"


# ---------------------------------------------------------------------------
# Retry budget: max_retries=2 allows up to 2 attempts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_budget_respected():
    hass = MockHass()
    hass.set_state("switch.tgt", "off")  # always off → every retry also fails

    manager = _make_manager(hass)
    mapping = _make_mapping(retry_delay=1, max_retries=2)
    mapping_id = mapping["id"]

    scheduled_delays: list[float] = []
    cancel_mock = MagicMock()

    def fake_call_later(h, delay, cb):
        scheduled_delays.append(delay)
        return cancel_mock

    with patch(
        "custom_components.ui_entity_mapper.manager.async_call_later",
        side_effect=fake_call_later,
    ):
        with patch(
            "custom_components.ui_entity_mapper.manager.async_dispatcher_send"
        ):
            # First execution (attempt 0)
            await manager._do_process_mapping(
                mapping, make_state("binary_sensor.src", "on"), reverse=False, force=True
            )
            assert len(scheduled_delays) == 1  # first retry scheduled

            # Simulate retry 1 executing (attempt 1)
            manager._pending_retries.pop(mapping_id, None)
            await manager._execute_retry(mapping, ("switch", "turn_on", {"entity_id": "switch.tgt"}), "switch.tgt", 1, 2)
            assert len(scheduled_delays) == 2  # second retry scheduled

            # Simulate retry 2 executing (attempt 2 = max)
            manager._pending_retries.pop(mapping_id, None)
            await manager._execute_retry(mapping, ("switch", "turn_on", {"entity_id": "switch.tgt"}), "switch.tgt", 1, 2)

    # After 2 retries, no further scheduling (budget 2 exhausted + the initial triggers 1)
    # Total: initial=1, retry1→schedule2, retry2→should NOT schedule (count=3 > max=2)
    assert len(scheduled_delays) == 2, f"Got {len(scheduled_delays)} scheduled delays"


# ---------------------------------------------------------------------------
# New source event cancels pending retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_event_cancels_pending_retry():
    hass = MockHass()
    hass.set_state("switch.tgt", "off")

    manager = _make_manager(hass)
    mapping = _make_mapping(retry_delay=60, max_retries=1)
    mapping_id = mapping["id"]

    cancel_mock = MagicMock()
    manager._pending_retries[mapping_id] = cancel_mock
    manager._retry_counts[mapping_id] = 1

    with patch(
        "custom_components.ui_entity_mapper.manager.async_call_later",
        return_value=MagicMock(),
    ):
        with patch("custom_components.ui_entity_mapper.manager.async_dispatcher_send"):
            await manager._do_process_mapping(
                mapping, make_state("binary_sensor.src", "off"), reverse=False, force=True
            )

    cancel_mock.assert_called_once()
    # Retry count reset to 0 by cancel
    assert manager._retry_counts.get(mapping_id, 0) == 0
