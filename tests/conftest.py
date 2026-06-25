"""Pytest fixtures and helpers for ui_entity_mapper tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockState:
    """Minimal HA State object substitute."""

    def __init__(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


class _StatesProxy:
    def __init__(self, store: dict[str, MockState]) -> None:
        self._store = store

    def get(self, entity_id: str) -> MockState | None:
        return self._store.get(entity_id)


class MockServices:
    """Records HA service calls for assertion in tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        blocking: bool = False,
    ) -> None:
        self.calls.append((domain, service, dict(data)))

    def last_call(self) -> tuple[str, str, dict[str, Any]] | None:
        return self.calls[-1] if self.calls else None

    def reset(self) -> None:
        self.calls.clear()


class MockHass:
    """Minimal hass substitute that tracks state and service calls."""

    def __init__(self) -> None:
        self._state_store: dict[str, MockState] = {}
        self.services = MockServices()

    @property
    def states(self) -> _StatesProxy:
        return _StatesProxy(self._state_store)

    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._state_store[entity_id] = MockState(entity_id, state, attributes or {})


@pytest.fixture
def mock_hass() -> MockHass:
    """Return a fresh MockHass instance."""
    return MockHass()


def make_state(
    entity_id: str,
    state: str,
    attributes: dict[str, Any] | None = None,
) -> MockState:
    """Convenience factory for a MockState."""
    return MockState(entity_id, state, attributes or {})
