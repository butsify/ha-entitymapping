"""Mapping manager for UI Entity Mapper.

The MappingManager is the runtime engine of the integration.  It:
  - Registers HA state-change listeners for all source (and bidirectional
    target) entities.
  - Applies mapping logic via mapper.py and calls the appropriate HA service.
  - Implements loop prevention using a per-entity write-timestamp guard.
  - Schedules configurable single/multi retries via async_call_later.
  - Exposes a MappingStatus dataclass that entity platforms read for dashboards.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    DOMAIN,
    LOOP_GUARD_WINDOW,
    SIGNAL_MAPPING_UPDATED,
    Direction,
    MappingMode,
)
from .mapper import (
    ServiceCall,
    check_boolean_target_reached,
    check_numeric_target_reached,
    compute_light_mirror_call,
    compute_service_call,
)
from .storage import MappingConfig

_LOGGER = logging.getLogger(__name__)


@dataclass
class MappingStatus:
    """Runtime diagnostics for a single mapping."""

    last_result: str = "pending"
    success_count: int = 0
    failure_count: int = 0
    last_error: str = ""
    last_retry_result: str = ""
    retry_count: int = 0


class MappingManager:
    """Manages the single mapping listener, loop prevention, and retry scheduling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Any,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self.entry_id = entry.entry_id

        # Unsubscribe callables for active HA state listeners
        self._unsub_listeners: list[Callable[[], None]] = []

        # entity_id → monotonic timestamp of last service call WE made to it
        self._loop_guard: dict[str, float] = {}

        # mapping_id → cancel handle for a pending async_call_later retry
        self._pending_retries: dict[str, Callable[[], None]] = {}

        # mapping_id → current retry attempt count (reset on new source event)
        self._retry_counts: dict[str, int] = {}

        # mapping_id → MappingStatus (created on demand)
        self._mapping_status: dict[str, MappingStatus] = {}

        # mapping_id → asyncio.Lock (serialises concurrent processing per mapping)
        self._mapping_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Register HA state listeners for the mapping."""
        mapping = self.get_mapping()
        self._mapping_status.setdefault(mapping["id"], MappingStatus())
        self._register_listeners()

    def _register_listeners(self) -> None:
        """(Re-)register state-change listeners for the mapping."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

        mapping = self.get_mapping()
        self._mapping_status.setdefault(mapping["id"], MappingStatus())

        sources: set[str] = {mapping["source_entity"]}
        targets_bidir: set[str] = set()
        if mapping["direction"] == Direction.BIDIRECTIONAL:
            targets_bidir.add(mapping["target_entity"])

        if sources:
            unsub = async_track_state_change_event(
                self.hass, list(sources), self._on_source_state_changed
            )
            self._unsub_listeners.append(unsub)

        if targets_bidir:
            unsub = async_track_state_change_event(
                self.hass, list(targets_bidir), self._on_target_state_changed
            )
            self._unsub_listeners.append(unsub)

    async def async_teardown(self) -> None:
        """Cancel all listeners and pending retries."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

        for cancel in self._pending_retries.values():
            cancel()
        self._pending_retries.clear()
        self._retry_counts.clear()

    # ------------------------------------------------------------------
    # Event callbacks (run in HA event loop, must be fast)
    # ------------------------------------------------------------------

    @callback
    def _on_source_state_changed(self, event: Event) -> None:
        """Fired when a source entity changes state."""
        entity_id: str = event.data["entity_id"]
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        for mapping in [self.get_mapping()]:
            if mapping["source_entity"] == entity_id:
                self.hass.async_create_task(
                    self._process_mapping(mapping, new_state, reverse=False)
                )

    @callback
    def _on_target_state_changed(self, event: Event) -> None:
        """Fired when a bidirectional target entity changes state."""
        entity_id: str = event.data["entity_id"]
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        for mapping in [self.get_mapping()]:
            if (
                mapping["target_entity"] == entity_id
                and mapping["direction"] == Direction.BIDIRECTIONAL
            ):
                self.hass.async_create_task(
                    self._process_mapping(mapping, new_state, reverse=True)
                )

    # ------------------------------------------------------------------
    # Core mapping processing
    # ------------------------------------------------------------------

    async def _process_mapping(
        self,
        mapping: MappingConfig,
        source_state_obj: Any,
        *,
        reverse: bool = False,
        force: bool = False,
    ) -> None:
        """Evaluate and execute the mapping for a given state change.

        Args:
            mapping: The mapping configuration to evaluate.
            source_state_obj: The HA State object of the triggering entity.
            reverse: True when processing the B→A direction in a bidirectional
                     mapping (source_state_obj is the *target* entity's state).
            force: When True, bypass loop-guard and lock (used by run_mapping_once).
        """
        mapping_id = mapping["id"]

        if not self._is_mapping_enabled(mapping):
            return

        # Serialise concurrent processing for the same mapping
        lock = self._mapping_locks.setdefault(mapping_id, asyncio.Lock())
        if not force and lock.locked():
            _LOGGER.debug("Skipping concurrent processing for mapping %s", mapping_id)
            return

        async with lock:
            await self._do_process_mapping(
                mapping, source_state_obj, reverse=reverse, force=force
            )

    async def _do_process_mapping(
        self,
        mapping: MappingConfig,
        source_state_obj: Any,
        *,
        reverse: bool,
        force: bool,
    ) -> None:
        """Inner processing logic (called while holding the mapping lock)."""
        mapping_id = mapping["id"]

        # In reverse mode the roles are swapped
        if reverse:
            actual_source = mapping["target_entity"]
            actual_target = mapping["source_entity"]
        else:
            actual_source = mapping["source_entity"]
            actual_target = mapping["target_entity"]

        # Loop-guard: if we recently wrote to actual_source, this event is our
        # own echo — suppress it to avoid ping-pong.
        if not force and mapping.get("prevent_loop", True):
            last_write = self._loop_guard.get(actual_source, 0.0)
            if time.monotonic() - last_write < LOOP_GUARD_WINDOW:
                _LOGGER.debug(
                    "Loop guard suppressed event on %s (mapping %s)",
                    actual_source,
                    mapping_id,
                )
                return

        # Cancel any stale retry — new event supersedes it
        self._cancel_pending_retry(mapping_id)

        # Compute the service call
        mode = mapping["mode"]
        transform = mapping.get("transform", {})

        if mode == MappingMode.LIGHT_MIRROR:
            call = compute_light_mirror_call(source_state_obj, actual_target, transform)
        else:
            call = compute_service_call(
                mode,
                source_state_obj.state,
                actual_source,
                actual_target,
                transform,
            )

        if call is None:
            _LOGGER.debug("No service call computed for mapping %s (state=%r)",
                          mapping_id, source_state_obj.state)
            return

        # Mark the target as written by us *before* the call so the listener
        # that fires after the state change sees the fresh guard timestamp.
        self._loop_guard[actual_target] = time.monotonic()

        success, err_msg = await self._execute_call(call)
        status = self._mapping_status.setdefault(mapping_id, MappingStatus())

        if success:
            status.last_result = "success"
            status.success_count += 1
            status.last_error = ""
        else:
            status.last_result = "failure"
            status.failure_count += 1
            if err_msg:
                status.last_error = err_msg

        async_dispatcher_send(
            self.hass,
            SIGNAL_MAPPING_UPDATED.format(mapping_id=mapping_id),
        )

        # Retry scheduling
        retry_delay = float(mapping.get("retry_delay_seconds", 0) or 0)
        max_retries = int(mapping.get("max_retries", 1) or 0)

        if retry_delay > 0 and max_retries > 0:
            target_reached = self._check_target_reached(mapping, call, actual_target)
            if not target_reached:
                self._schedule_retry(mapping, call, actual_target, retry_delay, max_retries)

    # ------------------------------------------------------------------
    # Service execution
    # ------------------------------------------------------------------

    async def _execute_call(self, call: ServiceCall) -> tuple[bool, str]:
        """Execute the given HA service call. Returns (success, error_message)."""
        domain, service, data = call
        try:
            await self.hass.services.async_call(
                domain, service, data, blocking=True
            )
            return True, ""
        except Exception as err:  # noqa: BLE001
            err_msg = str(err)
            _LOGGER.error("Service call %s.%s failed: %s", domain, service, err_msg)
            return False, err_msg

    # ------------------------------------------------------------------
    # Target-reached verification
    # ------------------------------------------------------------------

    def _check_target_reached(
        self,
        mapping: MappingConfig,
        call: ServiceCall,
        target_entity_id: str,
    ) -> bool:
        """Return True if the target is already in the expected state/value."""
        mode = mapping["mode"]
        _domain, service, data = call

        if mode in (MappingMode.BOOLEAN_MIRROR, MappingMode.NUMERIC_THRESHOLD,
                    MappingMode.LIGHT_MIRROR):
            # lock targets use "lock"/"unlock" instead of "turn_on"/"turn_off"
            if target_entity_id.split(".")[0] == "lock":
                expected_on = service == "lock"
            else:
                expected_on = service == "turn_on"
            return check_boolean_target_reached(self.hass, target_entity_id, expected_on)

        if mode in (MappingMode.NUMERIC_PASSTHROUGH, MappingMode.NUMERIC_SCALED):
            expected = float(data.get("value", 0))
            return check_numeric_target_reached(self.hass, target_entity_id, expected)

        return True  # Unknown mode → assume reached

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def _schedule_retry(
        self,
        mapping: MappingConfig,
        call: ServiceCall,
        target_entity_id: str,
        delay: float,
        max_retries: int,
    ) -> None:
        """Schedule the next retry attempt if the retry budget allows it."""
        mapping_id = mapping["id"]
        current_attempt = self._retry_counts.get(mapping_id, 0) + 1

        if current_attempt > max_retries:
            _LOGGER.debug(
                "Retry budget exhausted (%d/%d) for mapping %s",
                current_attempt - 1, max_retries, mapping_id,
            )
            return

        _LOGGER.debug(
            "Scheduling retry %d/%d for mapping %s in %.1fs",
            current_attempt, max_retries, mapping_id, delay,
        )
        self._retry_counts[mapping_id] = current_attempt

        @callback
        def _retry_callback(_now: Any) -> None:
            self._pending_retries.pop(mapping_id, None)
            self.hass.async_create_task(
                self._execute_retry(mapping, call, target_entity_id, delay, max_retries)
            )

        cancel = async_call_later(self.hass, delay, _retry_callback)
        self._pending_retries[mapping_id] = cancel

    async def _execute_retry(
        self,
        mapping: MappingConfig,
        call: ServiceCall,
        target_entity_id: str,
        delay: float,
        max_retries: int,
    ) -> None:
        """Execute one retry attempt; schedule the next if still not reached."""
        mapping_id = mapping["id"]

        # Check if target already reached (e.g., user fixed it manually)
        if self._check_target_reached(mapping, call, target_entity_id):
            _LOGGER.debug("Target already reached before retry for mapping %s", mapping_id)
            status = self._mapping_status.setdefault(mapping_id, MappingStatus())
            status.last_retry_result = "not_needed"
            async_dispatcher_send(
                self.hass,
                SIGNAL_MAPPING_UPDATED.format(mapping_id=mapping_id),
            )
            return

        self._loop_guard[target_entity_id] = time.monotonic()
        success, err_msg = await self._execute_call(call)

        status = self._mapping_status.setdefault(mapping_id, MappingStatus())
        status.last_retry_result = "success" if success else "failure"
        if success:
            status.success_count += 1
        else:
            status.failure_count += 1
            if err_msg:
                status.last_error = err_msg

        async_dispatcher_send(
            self.hass,
            SIGNAL_MAPPING_UPDATED.format(mapping_id=mapping_id),
        )

        # Schedule next retry if budget remains and target still not reached
        if not success or not self._check_target_reached(mapping, call, target_entity_id):
            self._schedule_retry(mapping, call, target_entity_id, delay, max_retries)

    def _cancel_pending_retry(self, mapping_id: str) -> None:
        """Cancel a scheduled retry and reset the attempt counter."""
        cancel = self._pending_retries.pop(mapping_id, None)
        if cancel is not None:
            cancel()
        self._retry_counts.pop(mapping_id, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_mapping_enabled(self, mapping: MappingConfig) -> bool:
        """Return the effective enabled state from the mapping config."""
        return bool(mapping.get("enabled", True))

    # ------------------------------------------------------------------
    # Public API (called by services and entity platforms)
    # ------------------------------------------------------------------

    async def enable_mapping(self, mapping_id: str) -> None:
        """Enable the mapping and persist via config entry."""
        new_data = {**self._entry.data, "enabled": True}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        async_dispatcher_send(
            self.hass,
            SIGNAL_MAPPING_UPDATED.format(mapping_id=mapping_id),
        )

    async def disable_mapping(self, mapping_id: str) -> None:
        """Disable the mapping, cancel pending retries, and persist."""
        self._cancel_pending_retry(mapping_id)
        new_data = {**self._entry.data, "enabled": False}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        async_dispatcher_send(
            self.hass,
            SIGNAL_MAPPING_UPDATED.format(mapping_id=mapping_id),
        )

    async def run_mapping_once(self, mapping_id: str) -> None:
        """Manually trigger the mapping once using the current source state."""
        mapping = self.get_mapping()
        if mapping["id"] != mapping_id:
            _LOGGER.error("run_mapping_once: mapping %s not found", mapping_id)
            return
        source_state = self.hass.states.get(mapping["source_entity"])
        if source_state is None:
            _LOGGER.warning(
                "run_mapping_once: source entity %s unavailable for mapping %s",
                mapping["source_entity"],
                mapping_id,
            )
            return
        # force=True bypasses loop-guard and lock so manual triggers always run
        await self._process_mapping(mapping, source_state, reverse=False, force=True)

    def get_status(self, mapping_id: str) -> MappingStatus:
        """Return current runtime status for a mapping (created on demand)."""
        return self._mapping_status.setdefault(mapping_id, MappingStatus())

    def get_all_mappings(self) -> list[MappingConfig]:
        """Return the single mapping for this entry."""
        return [self.get_mapping()]

    def get_mapping(self) -> MappingConfig:
        """Return the current mapping config from the live config entry."""
        return dict(self._entry.data)  # type: ignore[return-value]
