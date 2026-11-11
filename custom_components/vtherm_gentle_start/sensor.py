"""Sensor showing how far the Gentle Start setpoint is from the regulated temperature."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_entity_registry_updated_event, async_track_state_change_event

from .const import ATTR_GENTLE_START_SECTION, CONF_TARGET_VTHERM, DOMAIN, VT_DOMAIN

ICON_UP = "mdi:stairs-up"
ICON_DOWN = "mdi:stairs-down"
ICON_FLAT = "mdi:stairs"


def _number(value: Any) -> float | None:
    """A finite number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def adjustment_of(state: State | None) -> float | None:
    """The ramp setpoint minus the regulated temperature it is heading for, from the state of the thermostat.

    It is 0 when no ramp is in progress or the ramp has reached the regulated temperature, and None when the thermostat
    is not available or does not publish the ramp.
    """
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    section = state.attributes.get(ATTR_GENTLE_START_SECTION)
    if not isinstance(section, dict):
        return None
    ramp_value = _number(section.get("ramp_value"))
    if ramp_value is None:
        return 0.0
    # The regulated temperature of the thermostat is the adjusted setpoint, so the target of the ramp comes from its own section
    ramp_target = _number(section.get("ramp_target"))
    if ramp_target is None:
        return None
    # Adding 0.0 turns a negative zero into 0.0, which would otherwise show as -0.0
    return round(ramp_value - ramp_target, 1) + 0.0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Add the sensor of a thermostat."""
    async_add_entities([GentleStartAdjustmentSensor(hass, entry)])


class GentleStartAdjustmentSensor(SensorEntity):
    """The adjustment the ramp makes to the setpoint of a thermostat, in degrees.

    It is negative when heating and positive when cooling, while the ramp holds the setpoint back from the regulated
    temperature, and 0 otherwise. The icon follows the direction of the ramp: stairs up when the setpoint is rising towards
    the regulated temperature (negative adjustment), stairs down when it is falling towards it (positive adjustment).
    The sensor has its own device, connected to the thermostat, and follows the state of the thermostat entity.
    """

    # The name carries the name of the thermostat, so that the entity id does not depend on how Home Assistant composes it from the device
    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_suggested_display_precision = 1

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor of the thermostat the entry targets."""
        self._target = entry.data[CONF_TARGET_VTHERM]
        self._climate_entity_id: str | None = None
        self._unsubscribe_callbacks: list = []
        self._attr_unique_id = f"{entry.entry_id}_adjustment"
        # Not translated: the name has to carry the name of the thermostat, and Home Assistant only translates the name of an entity which has the device name in front of it
        self._attr_name = f"{entry.title} gentle start adjustment"
        # Home Assistant keeps one device per config entry, so the sensor cannot join the device of the thermostat: it has a device
        # of its own, which is shown as connected to the thermostat. The device of a thermostat is identified by the id of its entry.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{entry.title} Gentle Start",
            via_device=(VT_DOMAIN, self._target),
        )
        self._attr_native_unit_of_measurement = hass.config.units.temperature_unit
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @property
    def icon(self) -> str:
        """Stairs up while the setpoint rises towards the regulated temperature, down while it falls towards it."""
        value = self._attr_native_value
        if not value:
            return ICON_FLAT
        return ICON_UP if value < 0 else ICON_DOWN

    async def async_added_to_hass(self) -> None:
        """Follow the thermostat."""
        self._subscribe()
        self.async_on_remove(self._unsubscribe)

    @callback
    def _subscribe(self) -> None:
        """Find the entity of the thermostat and follow its state and its renaming."""
        self._unsubscribe()
        self._climate_entity_id = er.async_get(self.hass).async_get_entity_id(CLIMATE_DOMAIN, VT_DOMAIN, self._target)
        if self._climate_entity_id is None:
            self._update(None)
            return
        self._unsubscribe_callbacks = [
            async_track_state_change_event(self.hass, [self._climate_entity_id], self._on_state_changed),
            async_track_entity_registry_updated_event(self.hass, [self._climate_entity_id], self._on_registry_updated),
        ]
        self._update(self.hass.states.get(self._climate_entity_id))

    @callback
    def _unsubscribe(self) -> None:
        """Stop following the thermostat."""
        while self._unsubscribe_callbacks:
            self._unsubscribe_callbacks.pop()()

    @callback
    def _update(self, state: State | None) -> None:
        """Take the values from the state of the thermostat."""
        self._attr_native_value = adjustment_of(state)
        section = state.attributes.get(ATTR_GENTLE_START_SECTION) if state is not None else None
        action = section.get("action") if isinstance(section, dict) else None
        self._attr_extra_state_attributes = {"action": action} if action else {}

    @callback
    def _on_state_changed(self, event: Event) -> None:
        """The thermostat changed: its attributes carry the ramp."""
        self._update(event.data.get("new_state"))
        self.async_write_ha_state()

    @callback
    def _on_registry_updated(self, event: Event) -> None:
        """The entity of the thermostat was renamed or removed: look for it again."""
        if event.data.get("action") == "remove" or "entity_id" in event.data.get("changes", {}):
            self._subscribe()
            self.async_write_ha_state()
