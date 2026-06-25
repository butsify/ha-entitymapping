"""Sensor platform for UI Entity Mapper.

Three diagnostic sensors are created per mapping:
  - Last Result  : "success" / "failure" / "pending"
  - Success Count: cumulative count of successful executions
  - Failure Count: cumulative count of failed executions
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_MAPPING_UPDATED
from .manager import MappingManager, MappingStatus
from .storage import MappingConfig


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up three sensor entities per configured mapping."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    entities: list[SensorEntity] = []
    for mapping in manager.get_all_mappings():
        entities.append(MappingLastResultSensor(manager, mapping, entry.entry_id))
        entities.append(MappingSuccessCountSensor(manager, mapping, entry.entry_id))
        entities.append(MappingFailureCountSensor(manager, mapping, entry.entry_id))
    async_add_entities(entities)


class _MappingBaseSensor(SensorEntity):
    """Base class shared by all mapping diagnostic sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = False

    def __init__(
        self,
        manager: MappingManager,
        mapping: MappingConfig,
        entry_id: str,
        key: str,
        name_suffix: str,
    ) -> None:
        self._manager = manager
        self._mapping_id = mapping["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._mapping_id}_{key}"
        self._attr_name = f"{mapping['name']} — {name_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mapping["id"])},
            name=mapping["name"],
            manufacturer="UI Entity Mapper",
            model="Mapping Engine",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _status(self) -> MappingStatus:
        return self._manager.get_status(self._mapping_id)

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


class MappingLastResultSensor(_MappingBaseSensor):
    """Sensor showing the last execution result of a mapping."""

    def __init__(
        self, manager: MappingManager, mapping: MappingConfig, entry_id: str
    ) -> None:
        super().__init__(manager, mapping, entry_id, "last_result", "Last Result")

    @property
    def native_value(self) -> str:
        return self._status().last_result


class MappingSuccessCountSensor(_MappingBaseSensor):
    """Cumulative count of successful mapping executions."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "executions"
    _attr_icon = "mdi:check-circle-outline"

    def __init__(
        self, manager: MappingManager, mapping: MappingConfig, entry_id: str
    ) -> None:
        super().__init__(manager, mapping, entry_id, "success_count", "Success Count")

    @property
    def native_value(self) -> int:
        return self._status().success_count


class MappingFailureCountSensor(_MappingBaseSensor):
    """Cumulative count of failed mapping executions."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "executions"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self, manager: MappingManager, mapping: MappingConfig, entry_id: str
    ) -> None:
        super().__init__(manager, mapping, entry_id, "failure_count", "Failure Count")

    @property
    def native_value(self) -> int:
        return self._status().failure_count
