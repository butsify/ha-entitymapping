"""Persistent storage for UI Entity Mapper mappings."""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class TransformConfig(TypedDict, total=False):
    """Optional transform parameters for a mapping."""

    threshold: float
    input_min: float
    input_max: float
    output_min: float
    output_max: float
    invert: bool
    round: bool
    mirror_brightness: bool
    mirror_color_temp: bool


class MappingConfig(TypedDict):
    """Full configuration for a single mapping."""

    id: str
    name: str
    enabled: bool
    direction: str
    source_entity: str
    target_entity: str
    mode: str
    retry_delay_seconds: float
    max_retries: int
    prevent_loop: bool
    debounce_ms: int
    throttle_ms: int
    transform: TransformConfig


def _default_mapping(overrides: dict[str, Any]) -> MappingConfig:
    """Return a MappingConfig populated with defaults, overridden by *overrides*."""
    base: MappingConfig = {
        "id": str(uuid.uuid4()),
        "name": "New Mapping",
        "enabled": True,
        "direction": "unidirectional",
        "source_entity": "",
        "target_entity": "",
        "mode": "boolean_mirror",
        "retry_delay_seconds": 0.0,
        "max_retries": 1,
        "prevent_loop": True,
        "debounce_ms": 0,
        "throttle_ms": 0,
        "transform": {},
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


class MappingStorage:
    """Manages JSON persistence of mapping configurations via HA's Store helper."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._data: dict[str, Any] = {"mappings": []}

    async def async_load(self) -> None:
        """Load persisted data; initialises to empty if nothing stored yet."""
        data = await self._store.async_load()
        self._data = data if data is not None else {"mappings": []}

    async def async_save(self) -> None:
        """Atomically persist the current in-memory data."""
        await self._store.async_save(self._data)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_mappings(self) -> list[MappingConfig]:
        """Return all mappings."""
        return self._data.get("mappings", [])  # type: ignore[return-value]

    def get_mapping(self, mapping_id: str) -> MappingConfig | None:
        """Return a single mapping by ID, or None if not found."""
        for mapping in self.get_mappings():
            if mapping["id"] == mapping_id:
                return mapping
        return None

    # ------------------------------------------------------------------
    # Write helpers  (each one persists immediately)
    # ------------------------------------------------------------------

    async def add_mapping(self, config: dict[str, Any]) -> MappingConfig:
        """Append a new mapping (filling defaults) and save."""
        mapping = _default_mapping(config)
        self._data.setdefault("mappings", []).append(mapping)
        await self.async_save()
        return mapping

    async def update_mapping(self, mapping_id: str, updates: dict[str, Any]) -> bool:
        """Merge *updates* into an existing mapping and save. Returns True if found."""
        mappings: list[MappingConfig] = self._data.get("mappings", [])
        for i, mapping in enumerate(mappings):
            if mapping["id"] == mapping_id:
                self._data["mappings"][i] = {**mapping, **updates}
                await self.async_save()
                return True
        return False

    async def delete_mapping(self, mapping_id: str) -> bool:
        """Remove a mapping by ID and save. Returns True if found."""
        mappings: list[MappingConfig] = self._data.get("mappings", [])
        before = len(mappings)
        self._data["mappings"] = [m for m in mappings if m["id"] != mapping_id]
        if len(self._data["mappings"]) < before:
            await self.async_save()
            return True
        return False
