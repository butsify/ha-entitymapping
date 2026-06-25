"""Constants for UI Entity Mapper."""
from __future__ import annotations

from enum import StrEnum

DOMAIN = "ui_entity_mapper"
STORAGE_KEY = "ui_entity_mapper_mappings"
STORAGE_VERSION = 1

# Loop prevention: state changes on a target within this window after our
# own write are treated as echoes and suppressed.
LOOP_GUARD_WINDOW: float = 2.0  # seconds

DEFAULT_MAX_RETRIES: int = 1

# Dispatcher signal format string – use .format(mapping_id=id)
SIGNAL_MAPPING_UPDATED = f"{DOMAIN}_mapping_updated_{{mapping_id}}"

CONF_NAME = "name"
CONF_ENABLED = "enabled"
CONF_DIRECTION = "direction"
CONF_SOURCE_ENTITY = "source_entity"
CONF_TARGET_ENTITY = "target_entity"
CONF_MODE = "mode"
CONF_RETRY_DELAY = "retry_delay_seconds"
CONF_MAX_RETRIES = "max_retries"
CONF_PREVENT_LOOP = "prevent_loop"
CONF_DEBOUNCE_MS = "debounce_ms"
CONF_THROTTLE_MS = "throttle_ms"
CONF_TRANSFORM = "transform"


class MappingMode(StrEnum):
    """Supported mapping modes."""

    BOOLEAN_MIRROR = "boolean_mirror"
    NUMERIC_PASSTHROUGH = "numeric_passthrough"
    NUMERIC_SCALED = "numeric_scaled"
    NUMERIC_THRESHOLD = "numeric_threshold"
    LIGHT_MIRROR = "light_mirror"


class Direction(StrEnum):
    """Mapping direction."""

    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


# Valid source entity domains per mapping mode
MODE_VALID_SOURCE_DOMAINS: dict[str, list[str]] = {
    MappingMode.BOOLEAN_MIRROR: ["binary_sensor", "switch", "light"],
    MappingMode.NUMERIC_PASSTHROUGH: ["sensor", "number"],
    MappingMode.NUMERIC_SCALED: ["sensor", "number"],
    MappingMode.NUMERIC_THRESHOLD: ["sensor", "number"],
    MappingMode.LIGHT_MIRROR: ["light"],
}

# Valid target entity domains per mapping mode
MODE_VALID_TARGET_DOMAINS: dict[str, list[str]] = {
    MappingMode.BOOLEAN_MIRROR: ["switch", "light"],
    MappingMode.NUMERIC_PASSTHROUGH: ["number"],
    MappingMode.NUMERIC_SCALED: ["number", "light"],
    MappingMode.NUMERIC_THRESHOLD: ["switch", "light"],
    MappingMode.LIGHT_MIRROR: ["light"],
}

# All source domains that can appear in the entity selector
ALL_SOURCE_DOMAINS = ["binary_sensor", "switch", "sensor", "number", "light"]

# All target domains that can appear in the entity selector
ALL_TARGET_DOMAINS = ["switch", "number", "light"]
