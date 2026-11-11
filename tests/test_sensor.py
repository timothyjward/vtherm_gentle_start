"""Tests of the adjustment sensor."""

# pylint: disable=protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockEntityPlatform
import pytest

from custom_components.vtherm_gentle_start.const import CONF_MAX_STEP, CONF_START_OFFSET, CONF_TARGET_VTHERM, DOMAIN, VT_DOMAIN
from custom_components.vtherm_gentle_start import sensor as sensor_platform
from custom_components.vtherm_gentle_start.sensor import ICON_DOWN, ICON_FLAT, ICON_UP, GentleStartAdjustmentSensor, adjustment_of

CLIMATE = "climate.living_room"


def state(value: str = "heat", section: dict | None = None, regulated: object = 21.0) -> State:
    """A state of the thermostat with the Gentle Start section."""
    attributes: dict = {}
    if section is not None:
        attributes["gentle_start"] = {**section, "ramp_target": regulated}
    return State(CLIMATE, value, attributes)


@pytest.mark.parametrize(
    ("thermostat_state", "expected"),
    [
        # Heating: the ramp is below the regulated temperature
        (state(section={"ramp_value": 19.5, "action": "up"}), -1.5),
        # Cooling: the ramp is above it
        (state("cool", {"ramp_value": 24.5, "action": "up"}, regulated=23.0), 1.5),
        # The ramp has reached the regulated temperature
        (state(section={"ramp_value": 21.0, "action": "reached"}), 0.0),
        # The setpoint is below the regulated one by a floating point sliver only
        (state(section={"ramp_value": 20.7, "action": "up"}, regulated=20.7000000001), 0.0),
        # No ramp in progress
        (state("off", {"ramp_value": None, "action": None}), 0.0),
        # The thermostat is not available, has no plugin, or does not give the regulated temperature
        (state("unavailable", {"ramp_value": 19.5}), None),
        (state("unknown", {"ramp_value": 19.5}), None),
        (state(), None),
        (state(section={"ramp_value": 19.5}, regulated=None), None),
        (state(section={"ramp_value": 19.5}, regulated="21"), None),
        (state(section={"ramp_value": True}), 0.0),
        (state(section={"ramp_value": float("nan")}), 0.0),
        (None, None),
    ],
)
def test_adjustment_of(thermostat_state: State | None, expected: float | None) -> None:
    """The adjustment is the ramp setpoint minus the regulated temperature."""
    assert adjustment_of(thermostat_state) == expected


def test_a_negative_zero_is_a_zero() -> None:
    """-0.0 would show as a negative number."""
    value = adjustment_of(state(section={"ramp_value": 20.99}, regulated=21.0))
    assert str(value) == "0.0"


def sensor_for(hass: HomeAssistant, target: str = "vt-living") -> GentleStartAdjustmentSensor:
    """A sensor for a plugin entry which targets a thermostat."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TARGET_VTHERM: target, CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0})
    entry.add_to_hass(hass)
    return GentleStartAdjustmentSensor(hass, entry)


async def add_sensor(hass: HomeAssistant, sensor: GentleStartAdjustmentSensor) -> None:
    """Add the sensor to a platform, so that it can write its state."""
    platform = MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN)
    await platform.async_add_entities([sensor])
    await hass.async_block_till_done()


def register_climate(hass: HomeAssistant, entity_id: str = CLIMATE, unique_id: str = "vt-living") -> None:
    """Register the climate entity of a thermostat, as Versatile Thermostat does with the id of its config entry."""
    er.async_get(hass).async_get_or_create("climate", VT_DOMAIN, unique_id, suggested_object_id=entity_id.split(".")[1])


async def test_the_sensor_follows_the_thermostat(hass: HomeAssistant) -> None:
    """The value, the icon and the action follow the attributes of the thermostat."""
    register_climate(hass)
    hass.states.async_set(CLIMATE, "heat", {"gentle_start": {"ramp_target": 21.0, "ramp_value": 19.5, "action": "up"}})
    sensor = sensor_for(hass)
    await add_sensor(hass, sensor)

    assert sensor.native_value == -1.5
    assert sensor.icon == ICON_UP
    assert sensor.extra_state_attributes == {"action": "up"}
    assert sensor.native_unit_of_measurement == hass.config.units.temperature_unit

    hass.states.async_set(CLIMATE, "heat", {"gentle_start": {"ramp_target": 21.0, "ramp_value": 21.0, "action": "reached"}})
    await hass.async_block_till_done()
    assert sensor.native_value == 0.0
    assert sensor.icon == ICON_FLAT

    # Cooling: the ramp is above the regulated temperature and falling towards it
    hass.states.async_set(CLIMATE, "cool", {"gentle_start": {"ramp_target": 23.0, "ramp_value": 24.0, "action": "up"}})
    await hass.async_block_till_done()
    assert sensor.native_value == 1.0
    assert sensor.icon == ICON_DOWN

    hass.states.async_set(CLIMATE, "unavailable", {})
    await hass.async_block_till_done()
    assert sensor.native_value is None
    assert sensor.icon == ICON_FLAT
    assert sensor.extra_state_attributes == {}


async def test_the_sensor_has_a_device_connected_to_the_thermostat(hass: HomeAssistant) -> None:
    """Home Assistant keeps one device per config entry: the sensor has its own, connected to the device of the thermostat."""
    sensor = sensor_for(hass, "vt-bedroom")
    assert sensor.device_info["via_device"] == (VT_DOMAIN, "vt-bedroom")
    assert sensor.device_info["identifiers"] == {(DOMAIN, sensor.unique_id.removesuffix("_adjustment"))}
    assert sensor.unique_id.endswith("_adjustment")


async def test_no_thermostat_entity_is_unknown(hass: HomeAssistant) -> None:
    """A target which has no entity gives an unknown value, not an error."""
    sensor = sensor_for(hass, "vt-missing")
    await add_sensor(hass, sensor)
    assert sensor.native_value is None


async def test_the_sensor_follows_a_renamed_thermostat(hass: HomeAssistant) -> None:
    """The sensor finds the thermostat again when its entity id changes."""
    register_climate(hass)
    sensor = sensor_for(hass)
    await add_sensor(hass, sensor)

    er.async_get(hass).async_update_entity(CLIMATE, new_entity_id="climate.lounge")
    await hass.async_block_till_done()
    hass.states.async_set("climate.lounge", "heat", {"gentle_start": {"ramp_target": 21.0, "ramp_value": 20.0, "action": "up"}})
    await hass.async_block_till_done()
    assert sensor.native_value == -1.0


async def test_the_sensor_stops_following_when_removed(hass: HomeAssistant) -> None:
    """Nothing is left subscribed after the sensor is removed."""
    register_climate(hass)
    sensor = sensor_for(hass)
    await add_sensor(hass, sensor)
    assert sensor._unsubscribe_callbacks
    await sensor.async_remove()
    assert not sensor._unsubscribe_callbacks


async def test_the_platform_adds_one_sensor_per_entry(hass: HomeAssistant) -> None:
    """The setup of the platform creates the sensor of the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0})
    entry.add_to_hass(hass)
    added: list = []
    await sensor_platform.async_setup_entry(hass, entry, added.extend)
    assert len(added) == 1
    assert isinstance(added[0], GentleStartAdjustmentSensor)
    assert added[0].unique_id == f"{entry.entry_id}_adjustment"


async def test_the_sensor_waits_for_the_thermostat_to_publish_the_ramp(hass: HomeAssistant) -> None:
    """Right after the entry is added the thermostat has no Gentle Start section until it is reloaded: unknown, then the value."""
    register_climate(hass)
    hass.states.async_set(CLIMATE, "heat", {})
    sensor = sensor_for(hass)
    await add_sensor(hass, sensor)
    assert sensor.native_value is None

    hass.states.async_set(CLIMATE, "heat", {"gentle_start": {"ramp_target": 21.0, "ramp_value": 20.0, "action": "start"}})
    await hass.async_block_till_done()
    assert sensor.native_value == -1.0
    assert sensor.icon == ICON_UP


async def test_a_real_setup_connects_the_sensor_to_the_device_of_the_thermostat(hass: HomeAssistant) -> None:
    """Home Assistant sets the entry up: the sensor gets its own device, connected to the thermostat, and follows the thermostat."""
    vtherm = MockConfigEntry(domain=VT_DOMAIN, entry_id="vt-master", state=ConfigEntryState.LOADED)
    vtherm.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=vtherm.entry_id, identifiers={(VT_DOMAIN, "vt-master")}, name="Master bedroom")
    er.async_get(hass).async_get_or_create("climate", VT_DOMAIN, "vt-master", config_entry=vtherm, device_id=device.id, suggested_object_id="master_bedroom")
    hass.states.async_set("climate.master_bedroom", "heat", {"gentle_start": {"ramp_target": 21.0, "ramp_value": 19.5, "action": "up"}})

    plugin = MockConfigEntry(domain=DOMAIN, title="Master bedroom", data={CONF_TARGET_VTHERM: "vt-master", CONF_START_OFFSET: -0.5, CONF_MAX_STEP: 1.0})
    plugin.add_to_hass(hass)
    # The dependency is the thermostat integration, which is not set up here, and its entry must not be reloaded
    hass.config.components.add(VT_DOMAIN)
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(plugin.entry_id)
        await hass.async_block_till_done()

        entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{plugin.entry_id}_adjustment")
        assert entity_id == "sensor.master_bedroom_gentle_start_adjustment"
        sensor_device = dr.async_get(hass).async_get(er.async_get(hass).async_get(entity_id).device_id)
        assert sensor_device.identifiers == {(DOMAIN, plugin.entry_id)}
        assert sensor_device.name == "Master bedroom Gentle Start"
        assert sensor_device.via_device_id == device.id
        sensor_state = hass.states.get(entity_id)
        assert float(sensor_state.state) == -1.5
        assert sensor_state.attributes["icon"] == ICON_UP
        assert sensor_state.attributes["action"] == "up"
        assert sensor_state.attributes["unit_of_measurement"] == hass.config.units.temperature_unit

        # Removing the entry removes the sensor and leaves the device of the thermostat
        assert await hass.config_entries.async_remove(plugin.entry_id)
        await hass.async_block_till_done()
        assert er.async_get(hass).async_get(entity_id) is None
        assert dr.async_get(hass).async_get(device.id) is not None
        assert dr.async_get(hass).async_get(sensor_device.id) is None
