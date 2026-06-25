"""Config Flow and Options Flow for UI Entity Mapper.

Design decisions:
  - ConfigFlow: singleton entry — created with one click, no data required.
  - OptionsFlow: menu-driven multi-step flow for full CRUD on mappings.
    All mapping data is persisted via MappingStorage (not in config-entry
    options), so the options dict only carries a `_version` bump to trigger
    a reload on every save.
  - Mapping add/edit is split across two steps:
      1. Base settings  (name, entities, direction, retry)
      2. Mode + transform (filtered mode list, dynamic transform fields)
  - The flow uses `self._form_data` to carry step-1 answers into step-2.
"""
from __future__ import annotations

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
from .storage import MappingStorage


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
                            label="Unidirectional (source → target)",
                        ),
                        selector.SelectOptionDict(
                            value=Direction.BIDIRECTIONAL,
                            label="Bidirectional (source ↔ target)",
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
    """Handle the initial set-up of UI Entity Mapper.

    There is nothing to configure at this stage — the integration is a
    singleton helper that requires no credentials or host information.
    """

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "UiEntityMapperOptionsFlow":
        """Return the options flow handler."""
        return UiEntityMapperOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create the singleton config entry immediately."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="UI Entity Mapper", data={})


# ---------------------------------------------------------------------------
# Options Flow (full mapping CRUD)
# ---------------------------------------------------------------------------


class UiEntityMapperOptionsFlow(OptionsFlow):
    """Multi-step options flow providing add/edit/delete/toggle/duplicate for mappings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._editing_id: str | None = None
        # Accumulates step-1 data while step-2 is shown
        self._form_data: dict[str, Any] = {}
        # Cached storage instance for the duration of this flow
        self._storage: MappingStorage | None = None

    # ------------------------------------------------------------------
    # Storage accessor (lazy init — handles pre-reload state where
    # hass.data may not yet have the entry)
    # ------------------------------------------------------------------

    async def _get_storage(self) -> MappingStorage:
        if self._storage is not None:
            return self._storage
        domain_data = self.hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self._entry.entry_id, {})
        storage: MappingStorage | None = entry_data.get("storage")
        if storage is None:
            storage = MappingStorage(self.hass)
            await storage.async_load()
        self._storage = storage
        return storage

    # ------------------------------------------------------------------
    # Trigger reload by bumping a version counter in options
    # ------------------------------------------------------------------

    def _make_done_entry(self) -> dict[str, Any]:
        current = dict(self._entry.options)
        current["_version"] = int(current.get("_version", 0)) + 1
        return current

    # ------------------------------------------------------------------
    # Top-level menu
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show the main mapping management menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_mapping", "manage_mappings", "done"],
        )

    async def async_step_done(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Finish the options flow and trigger an integration reload."""
        return self.async_create_entry(data=self._make_done_entry())

    # ------------------------------------------------------------------
    # Add mapping — step 1: base settings
    # ------------------------------------------------------------------

    async def async_step_add_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect name, source/target entities, direction, retry settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            source_domain = _get_entity_domain(user_input.get("source_entity", ""))
            target_domain = _get_entity_domain(user_input.get("target_entity", ""))
            if not _get_valid_modes(source_domain, target_domain):
                errors["base"] = "no_valid_modes"
            if not errors:
                self._form_data = dict(user_input)
                self._editing_id = None
                return await self.async_step_add_mapping_mode()

        return self.async_show_form(
            step_id="add_mapping",
            data_schema=_base_mapping_schema(self._form_data or {}),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Add mapping — step 2: mode + transform
    # ------------------------------------------------------------------

    async def async_step_add_mapping_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect mode and transform parameters; save the new mapping."""
        return await self._step_mode_form(
            step_id="add_mapping_mode",
            user_input=user_input,
            is_edit=False,
        )

    # ------------------------------------------------------------------
    # Manage existing mappings
    # ------------------------------------------------------------------

    async def async_step_manage_mappings(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Present a list of existing mappings to select for management."""
        storage = await self._get_storage()
        mappings = storage.get_mappings()

        if not mappings:
            return self.async_show_form(
                step_id="manage_mappings",
                data_schema=vol.Schema({}),
                errors={"base": "no_mappings"},
            )

        if user_input is not None:
            self._editing_id = user_input["mapping_id"]
            return await self.async_step_mapping_menu()

        options = [
            selector.SelectOptionDict(
                value=m["id"],
                label=f"{m['name']}  [{'✓' if m['enabled'] else '✗'}  {m['mode'].replace('_', ' ')}]",
            )
            for m in mappings
        ]
        return self.async_show_form(
            step_id="manage_mappings",
            data_schema=vol.Schema(
                {
                    vol.Required("mapping_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # Per-mapping action menu
    # ------------------------------------------------------------------

    async def async_step_mapping_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show action choices for the selected mapping."""
        return self.async_show_menu(
            step_id="mapping_menu",
            menu_options=[
                "edit_mapping",
                "delete_mapping",
                "toggle_mapping",
                "duplicate_mapping",
                "back",
            ],
        )

    async def async_step_back(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return to the top-level menu."""
        return await self.async_step_init()

    # ------------------------------------------------------------------
    # Edit mapping — step 1
    # ------------------------------------------------------------------

    async def async_step_edit_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit base settings of the selected mapping."""
        storage = await self._get_storage()
        mapping = storage.get_mapping(self._editing_id) if self._editing_id else None
        errors: dict[str, str] = {}

        if user_input is not None:
            source_domain = _get_entity_domain(user_input.get("source_entity", ""))
            target_domain = _get_entity_domain(user_input.get("target_entity", ""))
            if not _get_valid_modes(source_domain, target_domain):
                errors["base"] = "no_valid_modes"
            if not errors:
                self._form_data = dict(user_input)
                return await self.async_step_edit_mapping_mode()

        defaults: dict[str, Any] = {}
        if mapping:
            defaults = {
                "name": mapping.get("name", ""),
                "source_entity": mapping.get("source_entity", ""),
                "target_entity": mapping.get("target_entity", ""),
                "direction": mapping.get("direction", Direction.UNIDIRECTIONAL),
                "enabled": mapping.get("enabled", True),
                "prevent_loop": mapping.get("prevent_loop", True),
                "retry_delay_seconds": mapping.get("retry_delay_seconds", 0),
                "max_retries": mapping.get("max_retries", 1),
            }

        return self.async_show_form(
            step_id="edit_mapping",
            data_schema=_base_mapping_schema(defaults),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Edit mapping — step 2
    # ------------------------------------------------------------------

    async def async_step_edit_mapping_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit mode and transform parameters of the selected mapping."""
        return await self._step_mode_form(
            step_id="edit_mapping_mode",
            user_input=user_input,
            is_edit=True,
        )

    # ------------------------------------------------------------------
    # Delete mapping (with confirmation)
    # ------------------------------------------------------------------

    async def async_step_delete_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Confirm and execute deletion of the selected mapping."""
        storage = await self._get_storage()
        mapping = storage.get_mapping(self._editing_id) if self._editing_id else None
        mapping_name = mapping["name"] if mapping else "Unknown"

        if user_input is not None:
            if self._editing_id:
                await storage.delete_mapping(self._editing_id)
            return await self.async_step_done()

        return self.async_show_form(
            step_id="delete_mapping",
            data_schema=vol.Schema({}),
            description_placeholders={"name": mapping_name},
        )

    # ------------------------------------------------------------------
    # Toggle enabled / disabled
    # ------------------------------------------------------------------

    async def async_step_toggle_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Flip the enabled flag of the selected mapping and save."""
        storage = await self._get_storage()
        if self._editing_id:
            mapping = storage.get_mapping(self._editing_id)
            if mapping:
                await storage.update_mapping(
                    self._editing_id, {"enabled": not mapping["enabled"]}
                )
        return await self.async_step_done()

    # ------------------------------------------------------------------
    # Duplicate mapping
    # ------------------------------------------------------------------

    async def async_step_duplicate_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Clone the selected mapping with a new UUID and '(copy)' suffix."""
        storage = await self._get_storage()
        if self._editing_id:
            mapping = storage.get_mapping(self._editing_id)
            if mapping:
                new_config = {
                    **mapping,
                    "id": str(uuid.uuid4()),
                    "name": f"{mapping['name']} (copy)",
                }
                await storage.add_mapping(new_config)
        return await self.async_step_done()

    # ------------------------------------------------------------------
    # Shared mode + transform form logic
    # ------------------------------------------------------------------

    async def _step_mode_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        is_edit: bool,
    ) -> dict[str, Any]:
        """Render and process the mode/transform form (shared by add and edit)."""
        storage = await self._get_storage()
        errors: dict[str, str] = {}

        source_entity = self._form_data.get("source_entity", "")
        target_entity = self._form_data.get("target_entity", "")
        source_domain = _get_entity_domain(source_entity)
        target_domain = _get_entity_domain(target_entity)
        valid_modes = _get_valid_modes(source_domain, target_domain)

        if not valid_modes:
            return self.async_show_form(
                step_id=step_id,
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
                    "mirror_brightness": bool(
                        user_input.get("mirror_brightness", True)
                    ),
                    "mirror_color_temp": bool(
                        user_input.get("mirror_color_temp", False)
                    ),
                }
                full_config: dict[str, Any] = {
                    **self._form_data,
                    "mode": mode,
                    "transform": transform,
                }
                if is_edit and self._editing_id:
                    await storage.update_mapping(self._editing_id, full_config)
                else:
                    await storage.add_mapping(full_config)
                return await self.async_step_done()

        # Build defaults (pre-fill for edit)
        transform_defaults: dict[str, Any] = {
            "threshold": 50.0,
            "input_min": 0.0,
            "input_max": 100.0,
            "output_min": 0.0,
            "output_max": 100.0,
            "invert": False,
            "round": False,
            "mirror_brightness": True,
            "mirror_color_temp": False,
        }
        mode_default = valid_modes[0]

        if is_edit and self._editing_id:
            existing = storage.get_mapping(self._editing_id)
            if existing:
                mode_default = existing.get("mode", valid_modes[0])
                transform = existing.get("transform", {})
                for k in transform_defaults:
                    if k in transform:
                        transform_defaults[k] = transform[k]

        schema_defaults = {"mode": mode_default, **transform_defaults}
        return self.async_show_form(
            step_id=step_id,
            data_schema=_mode_transform_schema(valid_modes, schema_defaults),
            errors=errors,
            description_placeholders={
                "source_domain": source_domain or "?",
                "target_domain": target_domain or "?",
            },
        )
