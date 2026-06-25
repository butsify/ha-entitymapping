"""Switch platform for UI Entity Mapper.

One MappingEnabledSwitch entity per configured mapping, placed on the
shared integration device.  Turning the switch on/off persists the change
and notifies the MappingManager.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up one enabled-switch entity per configured mapping."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    async_add_entities(
        MappingEnabledSwitch(manager, mapping, entry.entry_id)
        for mapping in manager.get_all_mappings()
    )


class MappingEnabledSwitch(SwitchEntity):
    """Switch that controls the enabled state of a single mapping."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = False

    def __init__(
        self,
        manager: MappingManager,
        mapping: MappingConfig,
        entry_id: str,
    ) -> None:
        self._manager = manager
        self._mapping_id = mapping["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._mapping_id}_enabled"
        self._attr_name = f"{mapping['name']} — Enabled"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="UI Entity Mapper",
            manufacturer="UI Entity Mapper",
            model="Mapping Engine",
            entry_type=DeviceEntryType.SERVICE,
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool:
        """Return True when the mapping is enabled."""
        mapping = self._manager.storage.get_mapping(self._mapping_id)
        return bool(mapping["enabled"]) if mapping else False

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the mapping."""
        await self._manager.enable_mapping(self._mapping_id)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the mapping."""
        await self._manager.disable_mapping(self._mapping_id)

    # ------------------------------------------------------------------
    # Dispatcher subscription
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to mapping status updates."""
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
