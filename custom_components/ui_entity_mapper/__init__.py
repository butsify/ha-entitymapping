"""UI Entity Mapper â€” integration entry point.

Each config entry represents one mapping. Responsibilities:
  - Create / tear down MappingManager on config-entry setup / unload.
  - Forward entity-platform setup to switch, sensor, text and button.
  - Register integration-wide services.
  - Reload the entry when options flow saves (triggers entity re-creation).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .manager import MappingManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "sensor", "text", "button"]

_SERVICE_SCHEMA_MAPPING_ID = vol.Schema(
    {vol.Required("mapping_id"): cv.string}
)
_SERVICE_SCHEMA_IMPORT = vol.Schema(
    {vol.Required("mappings"): list}
)


# ---------------------------------------------------------------------------
# Config entry lifecycle
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a single mapping config entry."""
    hass.data.setdefault(DOMAIN, {})

    manager = MappingManager(hass, entry)
    await manager.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {"manager": manager}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    # Reload the entry whenever the options flow saves (triggers entity re-creation)
    entry.async_on_unload(
        entry.add_update_listener(_async_reload_entry)
    )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options-update listener â€” reload the config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UI Entity Mapper config entry."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    await manager.async_teardown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Unregister services only when last entry is removed
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)

    return unload_ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_manager(hass: HomeAssistant, mapping_id: str) -> MappingManager | None:
    """Find the manager whose mapping has the given mapping_id."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        manager: MappingManager = entry_data.get("manager")
        if manager and manager.get_mapping().get("id") == mapping_id:
            return manager
    return None


# ---------------------------------------------------------------------------
# Service registration
# ---------------------------------------------------------------------------


def _async_register_services(hass: HomeAssistant) -> None:
    """Register all ui_entity_mapper services (idempotent â€” skips if already done)."""
    if hass.services.has_service(DOMAIN, "reload"):
        return

    async def _handle_reload(call: ServiceCall) -> None:
        for entry_data in hass.data.get(DOMAIN, {}).values():
            manager: MappingManager = entry_data["manager"]
            await hass.config_entries.async_reload(manager.entry_id)

    async def _handle_enable(call: ServiceCall) -> None:
        manager = _find_manager(hass, call.data["mapping_id"])
        if manager:
            await manager.enable_mapping(call.data["mapping_id"])
        else:
            _LOGGER.warning("enable_mapping: mapping %s not found", call.data["mapping_id"])

    async def _handle_disable(call: ServiceCall) -> None:
        manager = _find_manager(hass, call.data["mapping_id"])
        if manager:
            await manager.disable_mapping(call.data["mapping_id"])
        else:
            _LOGGER.warning("disable_mapping: mapping %s not found", call.data["mapping_id"])

    async def _handle_run_once(call: ServiceCall) -> None:
        manager = _find_manager(hass, call.data["mapping_id"])
        if manager:
            await manager.run_mapping_once(call.data["mapping_id"])
        else:
            _LOGGER.warning("run_mapping_once: mapping %s not found", call.data["mapping_id"])

    async def _handle_export(_call: ServiceCall) -> dict[str, Any]:
        mappings = [
            entry_data["manager"].get_mapping()
            for entry_data in hass.data.get(DOMAIN, {}).values()
            if "manager" in entry_data
        ]
        return {"mappings": mappings}

    async def _handle_import(call: ServiceCall) -> None:
        for mapping_data in call.data.get("mappings", []):
            if not isinstance(mapping_data, dict):
                _LOGGER.warning("import_mappings: skipping non-dict entry %r", mapping_data)
                continue
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=mapping_data,
            )

    hass.services.async_register(DOMAIN, "reload", _handle_reload)
    hass.services.async_register(
        DOMAIN, "enable_mapping", _handle_enable,
        schema=_SERVICE_SCHEMA_MAPPING_ID,
    )
    hass.services.async_register(
        DOMAIN, "disable_mapping", _handle_disable,
        schema=_SERVICE_SCHEMA_MAPPING_ID,
    )
    hass.services.async_register(
        DOMAIN, "run_mapping_once", _handle_run_once,
        schema=_SERVICE_SCHEMA_MAPPING_ID,
    )
    hass.services.async_register(
        DOMAIN, "export_mappings", _handle_export,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "import_mappings", _handle_import,
        schema=_SERVICE_SCHEMA_IMPORT,
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all integration services (called when last entry is unloaded)."""
    for name in [
        "reload",
        "enable_mapping",
        "disable_mapping",
        "run_mapping_once",
        "export_mappings",
        "import_mappings",
    ]:
        hass.services.async_remove(DOMAIN, name)


