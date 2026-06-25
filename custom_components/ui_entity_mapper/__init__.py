"""UI Entity Mapper — integration entry point.

Responsibilities:
  - Create / tear down MappingStorage and MappingManager on config-entry
    setup / unload.
  - Forward entity-platform setup to switch, sensor, text and button.
  - Register all integration services.
  - Register an options-update listener that reloads the entry whenever
    the options flow saves (triggering entity re-creation from fresh storage).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .manager import MappingManager
from .storage import MappingStorage

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
    """Set up UI Entity Mapper from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    storage = MappingStorage(hass)
    manager = MappingManager(hass, storage, entry.entry_id)
    await manager.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        "storage": storage,
        "manager": manager,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass, entry)

    # Reload the entry whenever the options flow saves (version bump)
    entry.async_on_unload(
        entry.add_update_listener(_async_reload_entry)
    )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options-update listener — reload the config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UI Entity Mapper config entry."""
    manager: MappingManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    await manager.async_teardown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _async_unregister_services(hass)

    return unload_ok


# ---------------------------------------------------------------------------
# Service registration
# ---------------------------------------------------------------------------


def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register all ui_entity_mapper services (idempotent — skips if already done)."""
    if hass.services.has_service(DOMAIN, "reload"):
        return

    entry_id = entry.entry_id

    def _manager() -> MappingManager:
        return hass.data[DOMAIN][entry_id]["manager"]

    def _storage() -> MappingStorage:
        return hass.data[DOMAIN][entry_id]["storage"]

    # ------------------------------------------------------------------

    async def _handle_reload(call: ServiceCall) -> None:
        await hass.config_entries.async_reload(entry_id)

    async def _handle_enable(call: ServiceCall) -> None:
        await _manager().enable_mapping(call.data["mapping_id"])

    async def _handle_disable(call: ServiceCall) -> None:
        await _manager().disable_mapping(call.data["mapping_id"])

    async def _handle_run_once(call: ServiceCall) -> None:
        await _manager().run_mapping_once(call.data["mapping_id"])

    async def _handle_export(_call: ServiceCall) -> dict[str, Any]:
        return {"mappings": _storage().get_mappings()}

    async def _handle_import(call: ServiceCall) -> None:
        storage = _storage()
        for mapping_data in call.data.get("mappings", []):
            if not isinstance(mapping_data, dict):
                _LOGGER.warning("import_mappings: skipping non-dict entry %r", mapping_data)
                continue
            if "id" not in mapping_data:
                mapping_data = {**mapping_data, "id": str(uuid.uuid4())}
            await storage.add_mapping(mapping_data)
        await hass.config_entries.async_reload(entry_id)

    # ------------------------------------------------------------------

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
    """Remove all integration services (called on unload)."""
    for name in [
        "reload",
        "enable_mapping",
        "disable_mapping",
        "run_mapping_once",
        "export_mappings",
        "import_mappings",
    ]:
        hass.services.async_remove(DOMAIN, name)
