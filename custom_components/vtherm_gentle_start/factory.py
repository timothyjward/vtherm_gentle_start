"""Factory for the Gentle Start feature manager plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import (
    CONF_THERMOSTAT_CLIMATE,
    CONF_THERMOSTAT_TYPE,
    FEATURE_MANAGER_GENTLE_START,
)
from .manager import GentleStartFeatureManager

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceFeatureManager, InterfaceThermostatRuntime


class GentleStartManagerFactory:
    """Create Gentle Start feature managers for eligible VTherm thermostats."""

    @property
    def name(self) -> str:
        """Return the feature manager identifier."""
        return FEATURE_MANAGER_GENTLE_START

    def supports(self, thermostat: "InterfaceThermostatRuntime") -> bool:
        """Return True for over_climate thermostats which regulate a setpoint.

        A direct valve regulation drives the valve opening, not a setpoint, so it never ramps.
        """
        try:
            entry_infos = thermostat.entry_infos
        except Exception:  # pylint: disable=broad-except
            return False
        if not isinstance(entry_infos, dict) or entry_infos.get(CONF_THERMOSTAT_TYPE) != CONF_THERMOSTAT_CLIMATE:
            return False
        return not getattr(thermostat, "have_valve_regulation", False)

    def create(self, thermostat: "InterfaceThermostatRuntime") -> "InterfaceFeatureManager":
        """Create a manager bound to the runtime thermostat."""
        return GentleStartFeatureManager(thermostat, thermostat.hass)
