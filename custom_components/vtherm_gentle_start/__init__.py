"""The vtherm_gentle_start integration."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import config_validation as cv

from vtherm_api.log_collector import get_vtherm_logger
from vtherm_api.vtherm_api import VThermAPI

from .const import CONF_TARGET_VTHERM, DOMAIN, FEATURE_MANAGER_GENTLE_START, VT_DOMAIN
from .factory import GentleStartManagerFactory

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = get_vtherm_logger(__name__)

#: Key in hass.data of the entries which have been set up since Home Assistant started.
DATA_ATTACHED = "attached"


def _register_factory(hass: HomeAssistant) -> bool:
    """Register the Gentle Start factory in the shared VT API."""
    api = VThermAPI.get_vtherm_api(hass)
    if api is None:
        _LOGGER.warning("Unable to register the Gentle Start factory because VThermAPI is unavailable")
        return False

    factory = GentleStartManagerFactory()
    if api.get_feature_manager(factory.name) is None:
        api.register_feature_manager(factory)
    return True


def _unregister_factory(hass: HomeAssistant) -> None:
    """Unregister the Gentle Start factory from the shared VT API."""
    api = VThermAPI.get_vtherm_api(hass)
    if api is not None:
        api.unregister_feature_manager(FEATURE_MANAGER_GENTLE_START)


def _attached(hass: HomeAssistant) -> set[str]:
    """The ids of the plugin entries whose thermostat has been given the chance to create its manager."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ATTACHED, set())


async def _reload_target_vtherm(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the thermostat the entry targets, so that it creates (or drops) its manager.

    The core reads the registered factories when a thermostat starts. A plugin entry added while Home Assistant is running
    would otherwise have no effect until the next restart. The thermostat is identified by the id of its config entry.
    """
    target = entry.data.get(CONF_TARGET_VTHERM)
    reloads = [
        hass.config_entries.async_reload(vtherm.entry_id)
        for vtherm in hass.config_entries.async_entries(VT_DOMAIN)
        if vtherm.entry_id == target and vtherm.state == ConfigEntryState.LOADED
    ]
    if reloads:
        _LOGGER.debug("Reloading the thermostat of the entry %s", entry.title)
        await asyncio.gather(*reloads)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up vtherm_gentle_start from YAML."""
    del config
    _register_factory(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up vtherm_gentle_start from a config entry.

    The managers read the options from the entry when they are used, so a change of the options
    needs no reload.
    """
    if not _register_factory(hass):
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # At startup the core picks the factory up when the thermostats start. Later it has to be asked to, once per entry:
    # the entry is also set up again when its options change, and the options are read when they are used.
    attached = _attached(hass)
    if entry.entry_id not in attached:
        attached.add(entry.entry_id)
        if hass.state == CoreState.running:
            await _reload_target_vtherm(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a vtherm_gentle_start config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    remaining = [other for other in hass.config_entries.async_entries(DOMAIN) if other.entry_id != entry.entry_id]
    if unloaded and not remaining:
        _unregister_factory(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the manager of the thermostat the removed entry targeted."""
    _attached(hass).discard(entry.entry_id)
    if hass.state != CoreState.running:
        return

    async def _reload_when_removed() -> None:
        # The entry is still listed while it is being removed, and the new manager would find it
        for _ in range(10):
            if hass.config_entries.async_get_entry(entry.entry_id) is None:
                break
            await asyncio.sleep(0)
        await _reload_target_vtherm(hass, entry)

    hass.async_create_task(_reload_when_removed())
