"""Config Flow and Options Flow for UI Entity Mapper.

Each config entry represents one mapping.
- ConfigFlow  : 2-step form to create a new mapping.
- OptionsFlow : 2-step form to edit an existing mapping.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ALL_SOURCE_DOMAINS,
    ALL_TARGET_DOMAINS,
    DOMAIN,
    Direction,
    MappingMode,
    MODE_VALID_SOURCE_DOMAINS,
    MODE_VALID_TARGET_DOMAINS,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _get_entity_domain(entity_id: str) -> str:
    """Extract the domain part of an entity_id."""
    return entity_id.split(".")[0] if "." in entity_id else ""


def _get_valid_modes(source_domain: str, target_domain: str) -> list[str]:
    """Return mapping modes that are valid for the given source/target domains."""
    return [
        mode
        for mode in MappingMode
        if source_domain in MODE_VALID_SOURCE_DOMAINS.get(mode, [])
        and target_domain in MODE_VALID_TARGET_DOMAINS.get(mode, [])
    ]


def _validate_mode_compat(
    source_domain: str, target_domain: str, mode: str
) -> str | None:
    """Return an error key if the combo is invalid, else None."""
    if source_domain not in MODE_VALID_SOURCE_DOMAINS.get(mode, []):
        return "invalid_source_for_mode"
    if target_domain not in MODE_VALID_TARGET_DOMAINS.get(mode, []):
        return "invalid_target_for_mode"
    return None


def _base_mapping_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the voluptuous schema for step 1 (base mapping settings)."""
    return vol.Schema(
        {
            vol.Required(
                "name", default=defaults.get("name", "")
            ): selector.TextSelector(),
            vol.Required(
                "source_entity", default=defaults.get("source_entity", "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=ALL_SOURCE_DOMAINS)
            ),
            vol.Required(
                "target_entity", default=defaults.get("target_entity", "")
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=ALL_TARGET_DOMAINS)
            ),
            vol.Required(
                "direction",
                default=defaults.get("direction", Direction.UNIDIRECTIONAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=Direction.UNIDIRECTIONAL,
                            label="Unidirectional (source â†’ target)",
                        ),
                        selector.SelectOptionDict(
                            value=Direction.BIDIRECTIONAL,
                            label="Bidirectional (source â†” target)",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                "enabled", default=defaults.get("enabled", True)
            ): selector.BooleanSelector(),
            vol.Required(
                "prevent_loop", default=defaults.get("prevent_loop", True)
            ): selector.BooleanSelector(),
            vol.Required(
                "retry_delay_seconds",
                default=defaults.get("retry_delay_seconds", 0),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3600, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                "max_retries",
                default=defaults.get("max_retries", 1),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=20, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _mode_transform_schema(
    valid_modes: list[str], defaults: dict[str, Any]
) -> vol.Schema:
    """Build the schema for step 2 (mode + transform parameters)."""
    mode_options = [
        selector.SelectOptionDict(
            value=m, label=m.replace("_", " ").title()
        )
        for m in valid_modes
    ]
    return vol.Schema(
        {
            vol.Required(
                "mode", default=defaults.get("mode", valid_modes[0])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=mode_options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(
                "threshold", default=defaults.get("threshold", 50.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-999999, max=999999, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "input_min", default=defaults.get("input_min", 0.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-999999, max=999999, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "input_max", default=defaults.get("input_max", 100.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-999999, max=999999, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "output_min", default=defaults.get("output_min", 0.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-999999, max=999999, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "output_max", default=defaults.get("output_max", 100.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-999999, max=999999, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                "invert", default=defaults.get("invert", False)
            ): selector.BooleanSelector(),
            vol.Optional(
                "round", default=defaults.get("round", False)
            ): selector.BooleanSelector(),
            vol.Optional(
                "mirror_brightness",
                default=defaults.get("mirror_brightness", True),
            ): selector.BooleanSelector(),
            vol.Optional(
                "mirror_color_temp",
                default=defaults.get("mirror_color_temp", False),
            ): selector.BooleanSelector(),
        }
    )


# ---------------------------------------------------------------------------
# Config Flow (one-shot entry creation)
# ---------------------------------------------------------------------------


class UiEntityMapperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle creation of a new mapping config entry (one entry per mapping)."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._form_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "UiEntityMapperOptionsFlow":
        """Return the options flow handler."""
        return UiEntityMapperOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 1: collect base mapping settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._form_data = {
                "id": str(uuid.uuid4()),
                "name": user_input["name"],
                "source_entity": user_input["source_entity"],
                "target_entity": user_input["target_entity"],
                "direction": user_input.get("direction", Direction.UNIDIRECTIONAL),
                "enabled": bool(user_input.get("enabled", True)),
                "prevent_loop": bool(user_input.get("prevent_loop", True)),
                "retry_delay_seconds": float(user_input.get("retry_delay_seconds", 0)),
                "max_retries": int(user_input.get("max_retries", 1)),
                "debounce_ms": 0,
                "throttle_ms": 0,
            }
            return await self.async_step_mode()
        return self.async_show_form(
            step_id="user",
            data_schema=_base_mapping_schema({}),
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: select mode and transform parameters."""
        errors: dict[str, str] = {}
        source_domain = _get_entity_domain(self._form_data.get("source_entity", ""))
        target_domain = _get_entity_domain(self._form_data.get("target_entity", ""))
        valid_modes = _get_valid_modes(source_domain, target_domain)

        if not valid_modes:
            return self.async_show_form(
                step_id="mode",
                data_schema=vol.Schema({}),
                errors={"base": "no_valid_modes"},
            )

        if user_input is not None:
            mode = user_input.get("mode", valid_modes[0])
            err = _validate_mode_compat(source_domain, target_domain, mode)
            if err:
                errors["mode"] = err
            else:
                transform = {
                    "threshold": float(user_input.get("threshold", 50.0)),
                    "input_min": float(user_input.get("input_min", 0.0)),
                    "input_max": float(user_input.get("input_max", 100.0)),
                    "output_min": float(user_input.get("output_min", 0.0)),
                    "output_max": float(user_input.get("output_max", 100.0)),
                    "invert": bool(user_input.get("invert", False)),
                    "round": bool(user_input.get("round", False)),
                    "mirror_brightness": bool(user_input.get("mirror_brightness", True)),
                    "mirror_color_temp": bool(user_input.get("mirror_color_temp", False)),
                }
                full_config = {**self._form_data, "mode": mode, "transform": transform}
                return self.async_create_entry(title=full_config["name"], data=full_config)

        return self.async_show_form(
            step_id="mode",
            data_schema=_mode_transform_schema(valid_modes, {}),
            description_placeholders={
                "source_domain": source_domain,
                "target_domain": target_domain,
            },
            errors=errors,
        )

    async def async_step_import(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a mapping entry from imported data (import_mappings service)."""
        if "id" not in user_input:
            user_input = {**user_input, "id": str(uuid.uuid4())}
        return self.async_create_entry(
            title=user_input.get("name", "Imported Mapping"), data=user_input
        )


# ---------------------------------------------------------------------------
# Options Flow (edits an existing mapping entry)
# ---------------------------------------------------------------------------


class UiEntityMapperOptionsFlow(OptionsFlow):
    """Two-step options flow to edit a single mapping."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._form_data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 1: edit base mapping settings (pre-filled from entry.data)."""
        defaults = dict(self._entry.data)
        errors: dict[str, str] = {}

        if user_input is not None:
            self._form_data = {
                "id": self._entry.data.get("id", str(uuid.uuid4())),
                "name": user_input["name"],
                "source_entity": user_input["source_entity"],
                "target_entity": user_input["target_entity"],
                "direction": user_input.get("direction", Direction.UNIDIRECTIONAL),
                "enabled": bool(user_input.get("enabled", True)),
                "prevent_loop": bool(user_input.get("prevent_loop", True)),
                "retry_delay_seconds": float(user_input.get("retry_delay_seconds", 0)),
                "max_retries": int(user_input.get("max_retries", 1)),
                "debounce_ms": 0,
                "throttle_ms": 0,
            }
            return await self.async_step_mode()

        return self.async_show_form(
            step_id="init",
            data_schema=_base_mapping_schema(defaults),
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: edit mode and transform parameters (pre-filled from entry.data)."""
        errors: dict[str, str] = {}
        source_domain = _get_entity_domain(self._form_data.get("source_entity", ""))
        target_domain = _get_entity_domain(self._form_data.get("target_entity", ""))
        valid_modes = _get_valid_modes(source_domain, target_domain)

        existing_transform = self._entry.data.get("transform", {})
        transform_defaults: dict[str, Any] = {
            "mode": self._entry.data.get(
                "mode", valid_modes[0] if valid_modes else "boolean_mirror"
            ),
            "threshold": float(existing_transform.get("threshold", 50.0)),
            "input_min": float(existing_transform.get("input_min", 0.0)),
            "input_max": float(existing_transform.get("input_max", 100.0)),
            "output_min": float(existing_transform.get("output_min", 0.0)),
            "output_max": float(existing_transform.get("output_max", 100.0)),
            "invert": bool(existing_transform.get("invert", False)),
            "round": bool(existing_transform.get("round", False)),
            "mirror_brightness": bool(existing_transform.get("mirror_brightness", True)),
            "mirror_color_temp": bool(existing_transform.get("mirror_color_temp", False)),
        }

        if not valid_modes:
            return self.async_show_form(
                step_id="mode",
                data_schema=vol.Schema({}),
                errors={"base": "no_valid_modes"},
            )

        if user_input is not None:
            mode = user_input.get("mode", valid_modes[0])
            err = _validate_mode_compat(source_domain, target_domain, mode)
            if err:
                errors["mode"] = err
            else:
                transform = {
                    "threshold": float(user_input.get("threshold", 50.0)),
                    "input_min": float(user_input.get("input_min", 0.0)),
                    "input_max": float(user_input.get("input_max", 100.0)),
                    "output_min": float(user_input.get("output_min", 0.0)),
                    "output_max": float(user_input.get("output_max", 100.0)),
                    "invert": bool(user_input.get("invert", False)),
                    "round": bool(user_input.get("round", False)),
                    "mirror_brightness": bool(user_input.get("mirror_brightness", True)),
                    "mirror_color_temp": bool(user_input.get("mirror_color_temp", False)),
                }
                new_config = {**self._form_data, "mode": mode, "transform": transform}
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    title=new_config["name"],
                    data=new_config,
                )
                return self.async_create_entry(
                    title=new_config["name"], data={"_v": int(time.time())}
                )

        return self.async_show_form(
            step_id="mode",
            data_schema=_mode_transform_schema(valid_modes, transform_defaults),
            description_placeholders={
                "source_domain": source_domain,
                "target_domain": target_domain,
            },
            errors=errors,
        )

