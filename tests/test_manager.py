"""Tests for the Gentle Start feature manager and its factory."""

# pylint: disable=protected-access

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vtherm_api import InterfaceSetpointModifier
from vtherm_api.interfaces import InterfaceFeatureManager

from custom_components.vtherm_gentle_start import manager as manager_module
from custom_components.vtherm_gentle_start.const import (
    ATTR_GENTLE_START_SECTION,
    COMMAND_CAUSE_UNDERLYING_TRACKING,
    CONF_MAX_STEP,
    CONF_START_OFFSET,
    CONF_TARGET_VTHERM,
    CONF_THERMOSTAT_CLIMATE,
    CONF_THERMOSTAT_TYPE,
    DOMAIN,
)
from custom_components.vtherm_gentle_start.factory import GentleStartManagerFactory
from custom_components.vtherm_gentle_start.manager import GentleStartFeatureManager

START = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


def make_thermostat(entries: list[dict], mode: str | None = "heat", room: float | None = 18.0, **extra) -> SimpleNamespace:
    """A fake runtime thermostat. ``entries`` are the data of the plugin entries."""
    hass = MagicMock()
    hass.config_entries.async_entries.side_effect = lambda domain: [SimpleNamespace(data=data) for data in entries] if domain == DOMAIN else []
    return SimpleNamespace(
        hass=hass,
        name="Living room",
        unique_id="vt-living",
        current_temperature=room,
        target_temperature=21.0,
        last_temperature_slope=None,
        vtherm_hvac_mode=mode,
        now=START,
        cycle_min=5,
        entry_infos={CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE},
        **extra,
    )


def make_manager(entries: list[dict] | None = None, **kwargs) -> tuple[GentleStartFeatureManager, SimpleNamespace]:
    """A manager on a fake thermostat. By default a plugin entry targets the thermostat."""
    if entries is None:
        entries = [{CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0}]
    thermostat = make_thermostat(entries, **kwargs)
    return GentleStartFeatureManager(thermostat, thermostat.hass), thermostat


def test_manager_satisfies_the_feature_manager_contract() -> None:
    """The manager implements every member of the feature manager protocol."""
    manager, _ = make_manager()
    assert isinstance(manager, InterfaceFeatureManager)
    assert isinstance(manager, InterfaceSetpointModifier)


def test_ramps_the_regulated_temperature() -> None:
    """The first setpoint is below the room temperature, then it moves one step per cycle."""
    manager, thermostat = make_manager()
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5
    assert manager.is_detected is True
    thermostat.now = START + timedelta(minutes=5)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 18.5


def test_not_configured_for_another_thermostat() -> None:
    """A plugin entry which targets another thermostat changes nothing here."""
    manager, _ = make_manager([{CONF_TARGET_VTHERM: "vt-bedroom"}])
    assert manager.is_configured is False
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 21
    assert manager.is_detected is False


def test_options_default_when_missing() -> None:
    """An entry without the options uses the defaults: offset -0.5 and step 1.0."""
    manager, thermostat = make_manager([{CONF_TARGET_VTHERM: "vt-living"}])
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5
    thermostat.now = START + timedelta(minutes=5)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 18.5


def test_options_are_read_when_used() -> None:
    """A change of the options is seen without reloading anything."""
    entries = [{CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: 1.0, CONF_MAX_STEP: 0.5}]
    manager, _ = make_manager(entries)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 19
    entries[0][CONF_START_OFFSET] = -1.0
    manager._ramp.reset()
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17


@pytest.mark.parametrize("mode", ["off", "fan_only", None])
def test_no_ramp_outside_heat_and_cool(mode) -> None:
    """The regulated temperature is returned as it is when the thermostat is not heating or cooling."""
    manager, _ = make_manager(mode=mode)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 21
    assert manager.is_detected is False


async def test_refresh_state_resets_the_ramp_when_off() -> None:
    """Switching off ends the ramp: the next switch-on starts a new one."""
    manager, thermostat = make_manager()
    manager.adjust_regulated_temperature(21, 0.5, None)
    assert manager.is_detected is True

    thermostat.vtherm_hvac_mode = "off"
    assert await manager.refresh_state() is False
    assert manager.is_detected is False

    thermostat.vtherm_hvac_mode = "heat"
    thermostat.current_temperature = 19.0
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 18.5


def test_underlying_tracking_is_followed() -> None:
    """The thermostat following the device is not ramped."""
    manager, _ = make_manager()
    assert manager.adjust_regulated_temperature(21, 0.5, COMMAND_CAUSE_UNDERLYING_TRACKING) == 21


def test_step_below_regulation_step_is_logged_once() -> None:
    """A maximum step below the rounding step is raised, with a single warning."""
    entries = [{CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 0.2}]
    manager, _ = make_manager(entries)
    with patch.object(manager_module, "_LOGGER") as logger:
        manager.adjust_regulated_temperature(21, 0.5, None)
        manager.adjust_regulated_temperature(21, 0.5, None)
    assert logger.warning.call_count == 1


def test_attributes() -> None:
    """The section of the thermostat attributes shows the options and the ramp position."""
    manager, _ = make_manager()
    manager.adjust_regulated_temperature(21, 0.5, None)
    attributes: dict = {}
    manager.add_custom_attributes(attributes)
    assert attributes[ATTR_GENTLE_START_SECTION] == {"start_offset": -0.5, "max_step": 1.0, "ramp_value": 17.5, "action": "start"}


def run_cycles(manager: GentleStartFeatureManager, thermostat: SimpleNamespace, rooms: list[float], slope: float | None) -> list[float]:
    """Run one regulation per cycle, with the room temperatures and the slope the thermostat reports."""
    sent = []
    for index, room in enumerate(rooms):
        thermostat.now = START + timedelta(minutes=5 * index)
        thermostat.current_temperature = room
        thermostat.last_temperature_slope = slope
        sent.append(manager.adjust_regulated_temperature(thermostat.target_temperature, 0.5, None))
    return sent


def test_the_ramp_follows_the_slope_of_the_thermostat() -> None:
    """A room which is rising fast towards the target stops the setpoint from rising."""
    manager, thermostat = make_manager()
    thermostat.target_temperature = 20.5
    # A degree per cycle is 12 degrees per hour: at the third cycle the room is predicted at 21, past the target of 20.5
    assert run_cycles(manager, thermostat, [18.0, 19.0, 20.0], 12.0) == [17.5, 18.5, 18.5]
    assert manager._ramp.action == "hold"


def test_the_slope_is_not_used_in_the_first_cycles() -> None:
    """The slope of the first cycles describes the room before the heating."""
    manager, thermostat = make_manager()
    thermostat.target_temperature = 20.5
    assert run_cycles(manager, thermostat, [20.0, 20.0], 12.0) == [19.5, 20.5]


def test_a_room_which_rises_slowly_does_not_slow_the_ramp() -> None:
    """A slope which does not take the room past the target changes nothing."""
    manager, thermostat = make_manager()
    assert run_cycles(manager, thermostat, [18.0, 18.2, 18.4], 2.4) == [17.5, 18.5, 19.5]


@pytest.mark.parametrize("slope", [None, math.nan, math.inf, -math.inf, "12", True, [12]])
def test_an_unknown_or_invalid_slope_changes_nothing(slope) -> None:
    """Without a usable slope the ramp is the plain ramp."""
    manager, thermostat = make_manager()
    thermostat.target_temperature = 20.5
    assert run_cycles(manager, thermostat, [18.0, 19.0, 20.0], slope) == [17.5, 18.5, 19.5]


@pytest.mark.parametrize(
    "mode, target, rooms, slope, expected",
    [
        # Heating: the room rises at a degree per cycle and would pass the target of 20.5
        ("heat", 20.5, [18.0, 19.0, 20.0], 12.0, [17.5, 18.5, 18.5]),
        # Cooling is the mirror: the room falls at a degree per cycle, the setpoint starts above the room, and is held below the target of 23.5
        ("cool", 23.5, [26.0, 25.0, 24.0], -12.0, [26.5, 25.5, 25.5]),
        # A slope in the wrong direction for the mode moves away from the target: the ramp is the plain ramp
        ("heat", 20.5, [18.0, 19.0, 20.0], -12.0, [17.5, 18.5, 19.5]),
        ("cool", 23.5, [26.0, 25.0, 24.0], 12.0, [26.5, 25.5, 24.5]),
    ],
)
def test_heating_and_cooling_follow_the_slope_in_their_own_direction(mode, target, rooms, slope, expected) -> None:
    """The manager gives the ramp the mode of the thermostat, so that the slope is read in the right direction."""
    manager, thermostat = make_manager(mode=mode)
    thermostat.target_temperature = target
    assert run_cycles(manager, thermostat, rooms, slope) == expected


def test_cooling_ramps_from_above_the_room_by_default() -> None:
    """With the default start offset a cooling thermostat starts above the room, never below the target, and goes down by a degree per cycle."""
    manager, thermostat = make_manager(mode="cool")
    thermostat.target_temperature = 23.0
    assert run_cycles(manager, thermostat, [26.0, 26.0, 25.5, 25.0, 24.5], None) == [26.5, 25.5, 24.5, 23.5, 23.0]


@pytest.mark.parametrize(
    "entry_infos, expected",
    [
        # The cycle is 5 minutes
        ({}, 300),
        ({"auto_regulation_periode_min": 15}, 900),
        # A period shorter than a cycle does not shorten the look-ahead
        ({"auto_regulation_periode_min": 2}, 300),
        ({"auto_regulation_periode_min": None}, 300),
        ({"auto_regulation_periode_min": "abc"}, 300),
    ],
)
def test_the_look_ahead_is_the_time_to_the_next_regulation(entry_infos, expected) -> None:
    """The room is predicted at the next regulation, which is at least a cycle away."""
    manager, thermostat = make_manager()
    thermostat.entry_infos = {CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE, **entry_infos}
    with patch.object(manager._ramp, "adjust", return_value=20.0) as adjust:
        manager.adjust_regulated_temperature(21, 0.5, None)
    assert adjust.call_args.kwargs["horizon_seconds"] == expected
    assert adjust.call_args.kwargs["target"] == 21.0


def test_a_thermostat_without_the_plugin_gets_no_attributes() -> None:
    """A thermostat which the plugin does not target keeps its attributes."""
    manager, _ = make_manager([{CONF_TARGET_VTHERM: "vt-bedroom"}])
    attributes: dict = {}
    manager.add_custom_attributes(attributes)
    assert attributes == {}


def test_restore_state_resumes_the_ramp() -> None:
    """After a restart the ramp resumes from the position saved in the attributes."""
    manager, thermostat = make_manager()
    manager.restore_state(SimpleNamespace(attributes={ATTR_GENTLE_START_SECTION: {"ramp_value": 19.5}}))
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 19.5
    thermostat.now = START + timedelta(minutes=5)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 20.5


@pytest.mark.parametrize("old_state", [None, SimpleNamespace(attributes={}), SimpleNamespace(attributes={ATTR_GENTLE_START_SECTION: {"ramp_value": None}})])
def test_restore_state_without_a_ramp(old_state) -> None:
    """Nothing is restored when no ramp was in progress."""
    manager, _ = make_manager()
    manager.restore_state(old_state)
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5


def test_restore_state_ignores_an_invalid_value() -> None:
    """A value which is not a number is ignored."""
    manager, _ = make_manager()
    manager.restore_state(SimpleNamespace(attributes={ATTR_GENTLE_START_SECTION: {"ramp_value": "abc"}}))
    assert manager.adjust_regulated_temperature(21, 0.5, None) == 17.5


def test_factory_supports_over_climate_only() -> None:
    """The factory creates a manager for over_climate thermostats without valve regulation."""
    factory = GentleStartManagerFactory()
    assert factory.name == "gentle_start"
    assert factory.supports(make_thermostat([])) is True
    assert factory.supports(make_thermostat([], have_valve_regulation=True)) is False
    over_switch = make_thermostat([])
    over_switch.entry_infos = {CONF_THERMOSTAT_TYPE: "thermostat_over_switch"}
    assert factory.supports(over_switch) is False
    no_infos = make_thermostat([])
    no_infos.entry_infos = None
    assert factory.supports(no_infos) is False


def test_factory_creates_a_manager() -> None:
    """The created manager is bound to the thermostat."""
    thermostat = make_thermostat([])
    manager = GentleStartManagerFactory().create(thermostat)
    assert isinstance(manager, GentleStartFeatureManager)
    assert str(manager) == "Living room"
    assert manager.name == "gentle_start"
    assert manager.hass is thermostat.hass
