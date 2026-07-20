"""Constants for UI Entity Mapper."""
from __future__ import annotations

from enum import StrEnum

DOMAIN = "ui_entity_mapper"

# Loop prevention: state changes on a target within this window after our
# own write are treated as echoes and suppressed.
LOOP_GUARD_WINDOW: float = 2.0  # seconds

# Dispatcher signal format string - use .format(mapping_id=id)
SIGNAL_MAPPING_UPDATED = f"{DOMAIN}_mapping_updated_{{mapping_id}}"


class MappingMode(StrEnum):
    """Supported mapping modes."""

    BOOLEAN_MIRROR = "boolean_mirror"
    NUMERIC_PASSTHROUGH = "numeric_passthrough"
    NUMERIC_SCALED = "numeric_scaled"
    NUMERIC_THRESHOLD = "numeric_threshold"
    LIGHT_MIRROR = "light_mirror"
    TEXT_PASSTHROUGH = "text_passthrough"
    LOXONE_TEXT_COMMAND = "loxone_text_command"


class Direction(StrEnum):
    """Mapping direction."""

    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


# Valid source entity domains per mapping mode
MODE_VALID_SOURCE_DOMAINS: dict[str, list[str]] = {
    MappingMode.BOOLEAN_MIRROR: ["binary_sensor", "switch", "light", "lock"],
    MappingMode.NUMERIC_PASSTHROUGH: ["sensor", "number"],
    MappingMode.NUMERIC_SCALED: ["sensor", "number"],
    MappingMode.NUMERIC_THRESHOLD: ["sensor", "number"],
    MappingMode.LIGHT_MIRROR: ["light"],
    MappingMode.TEXT_PASSTHROUGH: ["sensor", "text", "input_text"],
    MappingMode.LOXONE_TEXT_COMMAND: ["sensor", "text", "input_text"],
}

# Valid target entity domains per mapping mode
MODE_VALID_TARGET_DOMAINS: dict[str, list[str]] = {
    MappingMode.BOOLEAN_MIRROR: ["switch", "light", "lock"],
    MappingMode.NUMERIC_PASSTHROUGH: ["number"],
    MappingMode.NUMERIC_SCALED: ["number", "light"],
    MappingMode.NUMERIC_THRESHOLD: ["switch", "light", "lock"],
    MappingMode.LIGHT_MIRROR: ["light"],
    MappingMode.TEXT_PASSTHROUGH: ["text", "input_text"],
    MappingMode.LOXONE_TEXT_COMMAND: ["sensor"],
}

# All source domains that can appear in the entity selector
ALL_SOURCE_DOMAINS = ["binary_sensor", "switch", "sensor", "number", "light", "lock", "text", "input_text"]

# All target domains that can appear in the entity selector
ALL_TARGET_DOMAINS = ["switch", "number", "light", "lock", "text", "input_text", "sensor"]
