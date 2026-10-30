"""Tests of the setup of the entries: the thermostat they target has to be reloaded to take the plugin up while Home Assistant runs."""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vtherm_api.vtherm_api import VThermAPI

from custom_components.vtherm_gentle_start import async_remove_entry, async_setup_entry, async_unload_entry
from custom_components.vtherm_gentle_start.const import CONF_MAX_STEP, CONF_START_OFFSET, CONF_TARGET_VTHERM, DOMAIN, FEATURE_MANAGER_GENTLE_START, VT_DOMAIN


def add_vtherm(hass: HomeAssistant, entry_id: str, state: ConfigEntryState = ConfigEntryState.LOADED) -> MockConfigEntry:
    """A config entry of a Versatile Thermostat. Its id is the unique id of its thermostat."""
    entry = MockConfigEntry(domain=VT_DOMAIN, entry_id=entry_id, state=state)
    entry.add_to_hass(hass)
    return entry


def add_plugin_entry(hass: HomeAssistant, target: str) -> MockConfigEntry:
    """A plugin entry which targets a thermostat."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TARGET_VTHERM: target, CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(name="reload")
def reload_fixture(hass: HomeAssistant):
    """Replace the reload of config entries, to see which ones are reloaded."""
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as reload:
        yield reload


async def test_adding_an_entry_reloads_only_the_thermostat_it_targets(hass: HomeAssistant, reload: AsyncMock) -> None:
    """The core reads the factories when a thermostat starts: a thermostat which is running has to be started again to get its manager."""
    add_vtherm(hass, "vt-living")
    add_vtherm(hass, "vt-bedroom")
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    reload.assert_awaited_once_with("vt-living")


async def test_the_factory_is_registered_before_the_thermostat_is_reloaded(hass: HomeAssistant) -> None:
    """The reloaded thermostat must find the factory."""
    add_vtherm(hass, "vt-living")
    seen = []

    async def reload(entry_id: str) -> bool:
        seen.append(VThermAPI.get_vtherm_api(hass).get_feature_manager(FEATURE_MANAGER_GENTLE_START) is not None)
        return True

    with patch.object(hass.config_entries, "async_reload", reload):
        assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    assert seen == [True]


async def test_setting_the_entry_up_again_does_not_reload_the_thermostat(hass: HomeAssistant, reload: AsyncMock) -> None:
    """Changing the options sets the entry up again, and the options are read when used: the thermostat is left alone."""
    add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    assert await async_setup_entry(hass, entry)
    assert await async_unload_entry(hass, entry)
    assert await async_setup_entry(hass, entry)
    reload.assert_awaited_once_with("vt-living")


async def test_nothing_is_reloaded_while_home_assistant_starts(hass: HomeAssistant, reload: AsyncMock) -> None:
    """At startup the core picks the factory up by itself when the thermostats start."""
    hass.set_state(CoreState.starting)
    add_vtherm(hass, "vt-living")
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    reload.assert_not_awaited()
    assert VThermAPI.get_vtherm_api(hass).get_feature_manager(FEATURE_MANAGER_GENTLE_START) is not None


async def test_a_thermostat_which_is_not_loaded_is_not_reloaded(hass: HomeAssistant, reload: AsyncMock) -> None:
    """A thermostat which is not running will create its manager when it starts."""
    add_vtherm(hass, "vt-living", ConfigEntryState.NOT_LOADED)
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    reload.assert_not_awaited()


async def test_an_entry_for_an_unknown_thermostat_reloads_nothing(hass: HomeAssistant, reload: AsyncMock) -> None:
    """An entry whose thermostat has been deleted has nothing to reload."""
    add_vtherm(hass, "vt-living")
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-gone"))
    reload.assert_not_awaited()


async def test_removing_an_entry_reloads_its_thermostat_once_it_is_gone(hass: HomeAssistant) -> None:
    """The thermostat is reloaded to drop its manager, after the entry has left the list: else the new manager would still find it."""
    add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    still_listed = []

    async def reload(entry_id: str) -> bool:
        still_listed.append(hass.config_entries.async_get_entry(entry.entry_id) is not None)
        return True

    with patch.object(hass.config_entries, "async_reload", reload):
        assert await async_setup_entry(hass, entry)
        assert await async_unload_entry(hass, entry)
        still_listed.clear()
        await async_remove_entry(hass, entry)
        # The removal takes a few turns of the event loop to finish
        for _ in range(3):
            await asyncio.sleep(0)
        hass.config_entries._entries.pop(entry.entry_id)
        await hass.async_block_till_done()
    assert still_listed == [False]
    assert VThermAPI.get_vtherm_api(hass).get_feature_manager(FEATURE_MANAGER_GENTLE_START) is None


async def test_an_entry_which_is_added_again_reloads_its_thermostat_again(hass: HomeAssistant, reload: AsyncMock) -> None:
    """Removing an entry forgets that it was set up."""
    add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    assert await async_setup_entry(hass, entry)
    await async_remove_entry(hass, entry)
    hass.config_entries._entries.pop(entry.entry_id)
    await hass.async_block_till_done()
    reload.reset_mock()
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    reload.assert_awaited_once_with("vt-living")


async def test_removing_an_entry_while_home_assistant_stops_reloads_nothing(hass: HomeAssistant, reload: AsyncMock) -> None:
    """Nothing is restarted when Home Assistant is not running."""
    hass.set_state(CoreState.stopping)
    add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    await async_remove_entry(hass, entry)
    await hass.async_block_till_done()
    reload.assert_not_awaited()
