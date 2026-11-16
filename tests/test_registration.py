"""Tests of the registration of the factory when Versatile Thermostat drops its API object, which happens with its last entry."""

# pylint: disable=protected-access

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vtherm_api.vtherm_api import VThermAPI

from custom_components.vtherm_gentle_start import async_remove_entry, async_setup_entry, async_unload_entry
from custom_components.vtherm_gentle_start import registration
from custom_components.vtherm_gentle_start.const import CONF_MAX_STEP, CONF_START_OFFSET, CONF_TARGET_VTHERM, DOMAIN, VT_DOMAIN
from custom_components.vtherm_gentle_start.factory import GentleStartManagerFactory


class FakeVThermAPI(VThermAPI):
    """Stands for the API class of Versatile Thermostat, which is a subclass of the base one."""


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


@pytest.fixture(autouse=True)
def forward_fixture(hass: HomeAssistant):
    """The tests call the setup directly, on entries which Home Assistant is not setting up: the platforms are not forwarded."""
    with patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()), patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
    ):
        yield


@pytest.fixture(name="api")
def api_fixture(hass: HomeAssistant) -> FakeVThermAPI:
    """The API object which Versatile Thermostat has created."""
    return FakeVThermAPI.get_vtherm_api(hass)


@pytest.fixture(name="cycle")
def cycle_fixture(hass: HomeAssistant, api: FakeVThermAPI):
    """Replace the unload and the setup of the thermostat entries by what Versatile Thermostat does with its API object."""
    calls: list[tuple] = []

    async def unload(entry_id: str) -> bool:
        calls.append(("unload", entry_id))
        # Versatile Thermostat removes its API object when its last entry is unloaded
        hass.data.pop(VT_DOMAIN, None)
        return True

    async def setup(entry_id: str) -> bool:
        calls.append(("setup", entry_id, registration.is_registered(hass), type(registration.current_api(hass))))
        # The thermostat is built when it is set up: it creates the API object when it does not exist
        FakeVThermAPI.get_vtherm_api(hass)
        return True

    with patch.object(hass.config_entries, "async_unload", unload), patch.object(hass.config_entries, "async_setup", setup):
        yield calls


async def test_the_only_thermostat_is_reloaded_with_the_factory_registered(hass: HomeAssistant, cycle: list) -> None:
    """The API object goes with the unload: the factory is registered again with a new one, of the class of the first, before the set up."""
    add_vtherm(hass, "vt-living")
    assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    assert cycle == [("unload", "vt-living"), ("setup", "vt-living", True, FakeVThermAPI)]


async def test_a_thermostat_with_company_is_reloaded_as_before(hass: HomeAssistant, api: FakeVThermAPI) -> None:
    """The API object survives while another entry is loaded: the plain reload is enough."""
    add_vtherm(hass, "vt-living")
    add_vtherm(hass, "vt-other")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as reload, patch.object(
        hass.config_entries, "async_unload", AsyncMock()
    ) as unload:
        assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    reload.assert_awaited_once_with("vt-living")
    unload.assert_not_awaited()


async def test_a_thermostat_which_cannot_be_unloaded_is_left_alone(hass: HomeAssistant, api: FakeVThermAPI) -> None:
    """A failed unload leaves the entry as it is: it is not set up on top of it."""
    add_vtherm(hass, "vt-living")
    with patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=False)), patch.object(hass.config_entries, "async_setup", AsyncMock()) as setup:
        assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    setup.assert_not_awaited()


async def test_the_thermostat_is_set_up_again_when_the_registration_fails(hass: HomeAssistant, cycle: list) -> None:
    """Whatever happens, the thermostat must not be left unloaded."""
    add_vtherm(hass, "vt-living")
    plugin = add_plugin_entry(hass, "vt-living")
    with patch.object(registration, "register_factory", side_effect=[True, RuntimeError("no API")]):
        with pytest.raises(RuntimeError):
            await registration.reload_thermostat(hass, "vt-living")
    assert [call[0] for call in cycle] == ["unload", "setup"]
    assert plugin is not None


async def test_removing_the_last_entry_reloads_the_thermostat_without_the_factory(hass: HomeAssistant, cycle: list) -> None:
    """With no entry left, the thermostat has to come back without a manager."""
    add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    assert await async_setup_entry(hass, entry)
    assert await async_unload_entry(hass, entry)
    cycle.clear()
    await async_remove_entry(hass, entry)
    hass.config_entries._entries.pop(entry.entry_id)
    await hass.async_block_till_done()
    # Nothing creates the API object before the thermostat is set up, which creates it without the factory
    assert cycle == [("unload", "vt-living"), ("setup", "vt-living", False, type(None))]


async def test_another_entry_keeps_the_factory_when_one_is_removed(hass: HomeAssistant, cycle: list) -> None:
    """The factory is needed as long as an entry of the plugin exists."""
    add_vtherm(hass, "vt-living")
    add_vtherm(hass, "vt-other", ConfigEntryState.NOT_LOADED)
    first = add_plugin_entry(hass, "vt-living")
    add_plugin_entry(hass, "vt-other")
    assert await async_setup_entry(hass, first)
    cycle.clear()
    await async_remove_entry(hass, first)
    hass.config_entries._entries.pop(first.entry_id)
    await hass.async_block_till_done()
    assert cycle == [("unload", "vt-living"), ("setup", "vt-living", True, FakeVThermAPI)]


async def test_a_thermostat_reloaded_by_someone_else_is_restored(hass: HomeAssistant, cycle: list) -> None:
    """The user reloads the only thermostat: it comes back without the factory, and is reloaded again with it."""
    vtherm = add_vtherm(hass, "vt-living")
    plugin = add_plugin_entry(hass, "vt-living")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, plugin)
    cycle.clear()

    # What an options change does to the only thermostat: its API object is dropped, and a new one is created without the factory
    hass.data.pop(VT_DOMAIN, None)
    FakeVThermAPI.get_vtherm_api(hass)
    vtherm.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()

    assert cycle == [("unload", "vt-living"), ("setup", "vt-living", True, FakeVThermAPI)]


async def test_the_restoration_is_not_tried_twice(hass: HomeAssistant, cycle: list) -> None:
    """When the factory is still missing after the reload, reloading again would not help: it is left alone."""
    vtherm = add_vtherm(hass, "vt-living")
    plugin = add_plugin_entry(hass, "vt-living")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, plugin)
    cycle.clear()

    hass.data.pop(VT_DOMAIN, None)
    FakeVThermAPI.get_vtherm_api(hass)
    with patch.object(registration, "register_factory", return_value=False):
        vtherm.mock_state(hass, ConfigEntryState.LOADED)
        await hass.async_block_till_done()
        vtherm.mock_state(hass, ConfigEntryState.LOADED)
        await hass.async_block_till_done()
    assert [call[0] for call in cycle] == ["unload", "setup"]


async def test_a_thermostat_which_is_not_targeted_is_not_restored(hass: HomeAssistant, cycle: list) -> None:
    """Only the thermostats the plugin is attached to are reloaded."""
    add_vtherm(hass, "vt-living")
    other = add_vtherm(hass, "vt-other")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    cycle.clear()

    hass.data.pop(VT_DOMAIN, None)
    FakeVThermAPI.get_vtherm_api(hass)
    other.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()
    assert not cycle


async def test_a_thermostat_which_is_present_with_the_factory_is_left_alone(hass: HomeAssistant, cycle: list) -> None:
    """A thermostat which loads normally, with the factory registered, is not reloaded."""
    vtherm = add_vtherm(hass, "vt-living")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, add_plugin_entry(hass, "vt-living"))
    cycle.clear()
    vtherm.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()
    assert not cycle


async def test_the_watching_stops_with_the_last_entry(hass: HomeAssistant, cycle: list) -> None:
    """Once the plugin is unloaded, the thermostats are not watched any more."""
    vtherm = add_vtherm(hass, "vt-living")
    entry = add_plugin_entry(hass, "vt-living")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await async_setup_entry(hass, entry)
    assert await async_unload_entry(hass, entry)
    cycle.clear()
    hass.data.pop(VT_DOMAIN, None)
    FakeVThermAPI.get_vtherm_api(hass)
    vtherm.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()
    assert not cycle


async def test_a_thermostat_created_later_is_watched(hass: HomeAssistant, api: FakeVThermAPI) -> None:
    """The factory is asked to create the manager of each thermostat: it starts watching the entry of the thermostat."""
    vtherm = add_vtherm(hass, "vt-new")
    GentleStartManagerFactory().create(SimpleNamespace(hass=hass, unique_id="vt-new"))
    assert "vt-new" in hass.data[DOMAIN][registration.DATA_WATCHED]
    assert vtherm is not None


async def test_the_api_class_of_the_core_is_not_replaced_by_the_base_one(hass: HomeAssistant, api: FakeVThermAPI) -> None:
    """Registering when the API object has been dropped builds the next one with the class the core used."""
    registration.register_factory(hass)
    hass.data.pop(VT_DOMAIN, None)
    assert registration.current_api(hass) is None
    registration.register_factory(hass)
    assert type(registration.current_api(hass)) is FakeVThermAPI
    assert registration.is_registered(hass)
