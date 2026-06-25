"""Text platform for UI Entity Mapper.

One read-only text entity per mapping displays the last error message
produced by that mapping's execution.  The MappingManager writes to it
via dispatcher signals; users cannot set it directly (set_value is a no-op).
"""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_MAPPING_UPDATED
from .manager import MappingManager
from .storage import MappingConfig


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one last-error text entity per configured mapping."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    async_add_entities(
        MappingLastErrorText(manager, mapping, entry.entry_id)
        for mapping in manager.get_all_mappings()
    )


class MappingLastErrorText(TextEntity):
    """Read-only text entity that shows the last error for a mapping."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = False
    _attr_mode = "text"
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(
        self,
        manager: MappingManager,
        mapping: MappingConfig,
        entry_id: str,
    ) -> None:
        self._manager = manager
        self._mapping_id = mapping["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._mapping_id}_last_error"
        self._attr_name = f"{mapping['name']} — Last Error"
        self._attr_native_value = ""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="UI Entity Mapper",
            manufacturer="UI Entity Mapper",
            model="Mapping Engine",
            entry_type=DeviceEntryType.SERVICE,
        )

    # ------------------------------------------------------------------
    # State (pulled from manager status)
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> str:
        return self._manager.get_status(self._mapping_id).last_error

    # ------------------------------------------------------------------
    # Read-only: ignore any attempts to set the value from external callers
    # ------------------------------------------------------------------

    async def async_set_value(self, value: str) -> None:
        """This entity is managed by the integration; external writes are ignored."""

    # ------------------------------------------------------------------
    # Dispatcher subscription
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_MAPPING_UPDATED.format(mapping_id=self._mapping_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
