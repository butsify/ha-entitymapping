"""Diagnostics support for UI Entity Mapper."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .manager import MappingManager
from .storage import MappingStorage


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics data for the UI Entity Mapper config entry.

    Includes a snapshot of every mapping's configuration and its current
    runtime status (success/failure counts, last error, etc.).  No secrets
    or credentials are present in this integration, so no redaction is needed.
    """
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(config_entry.entry_id, {})

    storage: MappingStorage | None = entry_data.get("storage")
    manager: MappingManager | None = entry_data.get("manager")

    if storage is None or manager is None:
        return {"error": "Integration not fully initialised — data unavailable."}

    mappings_diag: dict[str, Any] = {}
    for mapping in storage.get_mappings():
        mid = mapping["id"]
        status = manager.get_status(mid)
        mappings_diag[mid] = {
            "config": {
                "name": mapping["name"],
                "enabled": mapping["enabled"],
                "source_entity": mapping["source_entity"],
                "target_entity": mapping["target_entity"],
                "mode": mapping["mode"],
                "direction": mapping["direction"],
                "retry_delay_seconds": mapping.get("retry_delay_seconds", 0),
                "max_retries": mapping.get("max_retries", 1),
                "prevent_loop": mapping.get("prevent_loop", True),
                "transform": mapping.get("transform", {}),
            },
            "status": {
                "last_result": status.last_result,
                "success_count": status.success_count,
                "failure_count": status.failure_count,
                "last_error": status.last_error,
                "last_retry_result": status.last_retry_result,
                "retry_count": status.retry_count,
            },
        }

    return {
        "entry_id": config_entry.entry_id,
        "mapping_count": len(storage.get_mappings()),
        "mappings": mappings_diag,
    }
