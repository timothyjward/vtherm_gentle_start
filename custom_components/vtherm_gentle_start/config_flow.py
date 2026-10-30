"""Config flow for vtherm_gentle_start."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_MAX_STEP,
    CONF_START_OFFSET,
    CONF_TARGET_VTHERM,
    DEFAULT_MAX_STEP,
    DEFAULT_START_OFFSET,
    DOMAIN,
    VT_DOMAIN,
)


def _number(minimum: float, maximum: float) -> selector.NumberSelector:
    """Build the selector of a temperature difference in degrees."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _options_schema(start_offset: float, max_step: float) -> dict[Any, Any]:
    """Build the fields of the two options, with their current values as defaults."""
    return {
        vol.Required(CONF_START_OFFSET, default=start_offset): _number(-5, 5),
        vol.Required(CONF_MAX_STEP, default=max_step): _number(0, 10),
    }


def _user_schema() -> vol.Schema:
    """Build the initial config schema (target VTherm and the two options)."""
    return vol.Schema(
        {
            vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN, integration=VT_DOMAIN)),
            **_options_schema(DEFAULT_START_OFFSET, DEFAULT_MAX_STEP),
        }
    )


def _reconfigure_schema(start_offset: float, max_step: float) -> vol.Schema:
    """Build the reconfigure schema (the two options only)."""
    return vol.Schema(_options_schema(start_offset, max_step))


class GentleStartConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage Gentle Start plugin config entries, one per thermostat."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Pick the over_climate VTherm to attach the ramp to."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_user_schema())

        entity_id = user_input[CONF_TARGET_VTHERM]
        reg_entry = er.async_get(self.hass).async_get(entity_id)
        if reg_entry is None or reg_entry.unique_id is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_user_schema(),
                errors={CONF_TARGET_VTHERM: "invalid_entity"},
            )

        target_unique_id = reg_entry.unique_id
        await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
        self._abort_if_unique_id_configured()

        state = self.hass.states.get(entity_id)
        return self.async_create_entry(
            title=state.name if state is not None else entity_id,
            data={
                CONF_TARGET_VTHERM: target_unique_id,
                CONF_START_OFFSET: user_input[CONF_START_OFFSET],
                CONF_MAX_STEP: user_input[CONF_MAX_STEP],
            },
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Edit the two options of an existing entry (the target is fixed)."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_reconfigure_schema(
                    entry.data.get(CONF_START_OFFSET, DEFAULT_START_OFFSET),
                    entry.data.get(CONF_MAX_STEP, DEFAULT_MAX_STEP),
                ),
            )
        return self.async_update_reload_and_abort(
            entry,
            data={
                **entry.data,
                CONF_START_OFFSET: user_input[CONF_START_OFFSET],
                CONF_MAX_STEP: user_input[CONF_MAX_STEP],
            },
        )
