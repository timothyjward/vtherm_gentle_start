"""Gentle Start feature manager for Versatile Thermostat over_climate thermostats.

The manager implements the ``InterfaceSetpointModifier`` extension of the
feature manager contract: the thermostat passes it the regulated temperature it
is about to send to the device, and the manager returns the setpoint to send
instead. The ramp itself lives in :mod:`.ramp`. The regulation period, the
regulation delta and the cycle stay under the control of Versatile Thermostat.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    ATTR_GENTLE_START_SECTION,
    CONF_AUTO_REGULATION_PERIOD_MIN,
    CONF_MAX_STEP,
    CONF_START_OFFSET,
    CONF_TARGET_VTHERM,
    DEFAULT_MAX_STEP,
    DEFAULT_START_OFFSET,
    DOMAIN,
    FEATURE_MANAGER_GENTLE_START,
)
from .ramp import SetpointRamp, effective_step, is_ramp_mode

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceThermostatRuntime

_LOGGER = get_vtherm_logger(__name__)


class GentleStartFeatureManager:
    """Feature manager limiting how fast the setpoint of a VTherm moves."""

    def __init__(self, thermostat: "InterfaceThermostatRuntime", hass: HomeAssistant) -> None:
        """Initialize the manager bound to a runtime thermostat."""
        self._vtherm = thermostat
        self._hass = hass
        self._ramp = SetpointRamp()
        self._step_warning_logged = False
        self._active_listener: list = []
        #: The regulated temperature the ramp is heading for: the value the thermostat gave at the last adjustment.
        self._desired: float | None = None

    # ------------------------------------------------------------------
    # Lifecycle (InterfaceFeatureManager contract)
    # ------------------------------------------------------------------
    def post_init(self, entry_infos: Any) -> None:
        """Nothing to read: the options are read from the plugin entry when they are used."""
        del entry_infos

    async def start_listening(self, force: bool = False) -> None:
        """Listen to the state of the thermostat to see it go off."""
        del force
        self.stop_listening()
        entity_id = self._vtherm.entity_id
        if entity_id:
            self._active_listener.append(async_track_state_change_event(self._hass, [entity_id], self._on_vtherm_state_changed))

    def stop_listening(self) -> bool | None:
        """Remove all active listeners."""
        while self._active_listener:
            self._active_listener.pop()()
        return None

    async def refresh_state(self) -> bool:
        """Forget the ramp when the thermostat is not heating or cooling, so that the next start is a new ramp."""
        if self._ramp.value is not None and not is_ramp_mode(self._mode):
            _LOGGER.debug("%s - the thermostat is not heating or cooling, the ramp is reset", self)
            self._ramp.reset()
        return False

    @callback
    def _on_vtherm_state_changed(self, event: Event) -> None:
        """Forget the ramp as soon as the thermostat is switched off.

        The control loop does not always call refresh_state for an OFF (it can return early, and an OFF followed
        quickly by a restart can happen between two cycles), so the state of the thermostat is watched as well.
        """
        new_state = event.data.get("new_state")
        if new_state is not None and new_state.state == "off" and self._ramp.value is not None:
            _LOGGER.debug("%s - the thermostat is off, the ramp is reset", self)
            self._ramp.reset()

    def restore_state(self, old_state: Any) -> None:
        """Resume the ramp which was in progress before Home Assistant restarted."""
        section = old_state.attributes.get(ATTR_GENTLE_START_SECTION) if old_state is not None else None
        value = section.get("ramp_value") if isinstance(section, dict) else None
        if value is None:
            return
        try:
            self._ramp.restore(float(value))
        except (TypeError, ValueError):
            _LOGGER.warning("%s - cannot restore the ramp setpoint from %s", self, value)
        else:
            _LOGGER.debug("%s - the ramp setpoint %.1f has been restored", self, float(value))

    def add_listener(self, func) -> None:
        """Add a callback to be removed on stop."""
        self._active_listener.append(func)

    def add_custom_attributes(self, extra_state_attributes: dict[str, Any]) -> None:
        """Expose the ramp under a dedicated top-level section, for a thermostat which has the plugin only: the others keep their attributes."""
        if not self.is_configured:
            return
        extra_state_attributes[ATTR_GENTLE_START_SECTION] = {
            "start_offset": self._option(CONF_START_OFFSET, DEFAULT_START_OFFSET),
            "max_step": self._option(CONF_MAX_STEP, DEFAULT_MAX_STEP),
            "ramp_value": self._ramp.value,
            # The thermostat shows the adjusted setpoint as its regulated temperature, so the value the ramp heads for is published here
            "ramp_target": self._desired if self._ramp.value is not None else None,
            "action": self._ramp.action,
        }

    # ------------------------------------------------------------------
    # InterfaceSetpointModifier contract
    # ------------------------------------------------------------------
    def adjust_regulated_temperature(self, desired: float, regulation_step: float, command_cause: str | None) -> float | None:
        """Return the setpoint to send for the regulated temperature computed by the thermostat."""
        mode = self._mode
        if not self.is_configured or not is_ramp_mode(mode):
            self._ramp.reset()
            self._desired = None
            return desired

        max_step = self._option(CONF_MAX_STEP, DEFAULT_MAX_STEP)
        _, raised = effective_step(max_step, regulation_step)
        if raised and not self._step_warning_logged:
            _LOGGER.warning(
                "%s - the ramp maximum step (%.2f) is lower than the regulation step (%.2f). The regulation step is used instead",
                self,
                max_step,
                regulation_step,
            )
            self._step_warning_logged = True

        self._desired = desired
        return self._ramp.adjust(
            desired,
            regulation_step,
            command_cause,
            mode=mode,
            current_temperature=self._vtherm.current_temperature,
            now=self._vtherm.now,
            cycle_seconds=self._cycle_seconds,
            start_offset=self._option(CONF_START_OFFSET, DEFAULT_START_OFFSET),
            max_step=max_step,
            target=self._vtherm.target_temperature,
            slope_per_hour=self._slope_per_hour,
            horizon_seconds=max(self._cycle_seconds, self._regulation_period_seconds),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        """The stable name of the feature manager."""
        return FEATURE_MANAGER_GENTLE_START

    @property
    def hass(self) -> HomeAssistant:
        """The Home Assistant instance."""
        return self._hass

    @property
    def is_configured(self) -> bool:
        """True when the user has added the plugin for this thermostat."""
        return self._entry_data() is not None

    @property
    def is_detected(self) -> bool:
        """True while a ramp is in progress."""
        return self._ramp.value is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @property
    def _mode(self) -> str | None:
        """The HVAC mode of the thermostat as a string."""
        mode = self._vtherm.vtherm_hvac_mode
        return None if mode is None else str(mode)

    @property
    def _cycle_seconds(self) -> float:
        """The cycle duration of the thermostat."""
        return self._vtherm.cycle_min * 60

    @property
    def _regulation_period_seconds(self) -> float:
        """The minimum time between two regulations of the thermostat, 0 when it is not set."""
        try:
            return float(self._vtherm.entry_infos.get(CONF_AUTO_REGULATION_PERIOD_MIN) or 0) * 60
        except (AttributeError, TypeError, ValueError):
            return 0.0

    @property
    def _slope_per_hour(self) -> float | None:
        """The slope of the room temperature computed by the thermostat, in degrees per hour. None when it is unknown or not a number."""
        slope = self._vtherm.last_temperature_slope
        if isinstance(slope, bool) or not isinstance(slope, (int, float)) or not math.isfinite(slope):
            return None
        return float(slope)

    def _entry_data(self) -> dict[str, Any] | None:
        """The data of the plugin entry targeting this thermostat, None when there is none."""
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_TARGET_VTHERM) == self._vtherm.unique_id:
                return entry.data
        return None

    def _option(self, key: str, default: float) -> float:
        """Read a numeric option of the plugin entry."""
        data = self._entry_data()
        value = data.get(key) if data is not None else None
        return float(value) if value is not None else default

    def __str__(self) -> str:
        """The thermostat name, for the logs."""
        return self._vtherm.name
