"""Button platform for UI Entity Mapper.

One button entity per mapping lets the user manually trigger a mapping
from the dashboard or via automations, regardless of the source entity's
current state.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .manager import MappingManager
from .storage import MappingConfig


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one run-once button entity per configured mapping."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    async_add_entities(
        MappingRunOnceButton(manager, mapping, entry.entry_id)
        for mapping in manager.get_all_mappings()
    )


class MappingRunOnceButton(ButtonEntity):
    """Stateless button that manually triggers a mapping once."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = False
    _attr_icon = "mdi:play-circle-outline"

    def __init__(
        self,
        manager: MappingManager,
        mapping: MappingConfig,
        entry_id: str,
    ) -> None:
        self._manager = manager
        self._mapping_id = mapping["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._mapping_id}_run_once"
        self._attr_name = f"{mapping['name']} — Run Once"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mapping["id"])},
            name=mapping["name"],
            manufacturer="UI Entity Mapper",
            model="Mapping Engine",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Manually execute the mapping for the current source state."""
        await self._manager.run_mapping_once(self._mapping_id)
