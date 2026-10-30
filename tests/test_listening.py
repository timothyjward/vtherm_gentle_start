"""Tests of the state listener which resets the ramp when the thermostat is switched off."""

# pylint: disable=protected-access

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vtherm_gentle_start.const import (
    CONF_MAX_STEP,
    CONF_START_OFFSET,
    CONF_TARGET_VTHERM,
    CONF_THERMOSTAT_CLIMATE,
    CONF_THERMOSTAT_TYPE,
    DOMAIN,
)
from custom_components.vtherm_gentle_start.manager import GentleStartFeatureManager

ENTITY_ID = "climate.living_room"
START = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


def make_manager(hass: HomeAssistant, entity_id: str | None = ENTITY_ID) -> tuple[GentleStartFeatureManager, SimpleNamespace]:
    """A manager on a fake thermostat, with a plugin entry which targets it, on a real Home Assistant."""
    MockConfigEntry(domain=DOMAIN, data={CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0}).add_to_hass(hass)
    thermostat = SimpleNamespace(
        hass=hass,
        entity_id=entity_id,
        name="Living room",
        unique_id="vt-living",
        current_temperature=18.0,
        target_temperature=21.0,
        last_temperature_slope=None,
        vtherm_hvac_mode="heat",
        now=START,
        cycle_min=5,
        entry_infos={CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE},
    )
    return GentleStartFeatureManager(thermostat, hass), thermostat


async def test_switching_off_resets_the_ramp(hass: HomeAssistant) -> None:
    """The ramp is forgotten when the state of the thermostat becomes off, even if no cycle saw it."""
    manager, thermostat = make_manager(hass)
    await manager.start_listening()

    hass.states.async_set(ENTITY_ID, "heat")
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5
    assert manager.is_detected is True

    # The thermostat is off, then heating again, before any cycle runs
    hass.states.async_set(ENTITY_ID, "off")
    await hass.async_block_till_done()
    assert manager.is_detected is False

    hass.states.async_set(ENTITY_ID, "heat")
    await hass.async_block_till_done()
    thermostat.current_temperature = 19.0
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 18.5

    manager.stop_listening()


async def test_other_states_keep_the_ramp(hass: HomeAssistant) -> None:
    """A state change which is not off does not touch the ramp."""
    manager, _ = make_manager(hass)
    await manager.start_listening()

    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5
    for state in ("heat", "cool", "unavailable"):
        hass.states.async_set(ENTITY_ID, state)
        await hass.async_block_till_done()
        assert manager.is_detected is True

    manager.stop_listening()


async def test_stop_listening_removes_the_listener(hass: HomeAssistant) -> None:
    """After stop_listening the state of the thermostat is no longer watched, and restarting does not add a second listener."""
    manager, _ = make_manager(hass)
    await manager.start_listening()
    await manager.start_listening()
    assert len(manager._active_listener) == 1

    manager.stop_listening()
    assert not manager._active_listener

    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5
    hass.states.async_set(ENTITY_ID, "off")
    await hass.async_block_till_done()
    assert manager.is_detected is True


async def test_no_listener_without_entity_id(hass: HomeAssistant) -> None:
    """A thermostat which has no entity id yet is not listened to."""
    manager, _ = make_manager(hass, entity_id=None)
    await manager.start_listening()
    assert not manager._active_listener
