"""Constants for the vtherm_gentle_start integration."""

from __future__ import annotations

DOMAIN = "vtherm_gentle_start"

#: Stable name of the feature manager in the VTherm API registry.
FEATURE_MANAGER_GENTLE_START = "gentle_start"

#: Versatile Thermostat domain, and the key and value identifying an over_climate entry.
VT_DOMAIN = "versatile_thermostat"
CONF_THERMOSTAT_TYPE = "thermostat_type"
CONF_THERMOSTAT_CLIMATE = "thermostat_over_climate"

#: Command cause set by the core when the thermostat follows a change made on the device.
COMMAND_CAUSE_UNDERLYING_TRACKING = "underlying_tracking"

#: Values of the VTherm HVAC mode the ramp cares about.
VTHERM_HVAC_MODE_HEAT = "heat"
VTHERM_HVAC_MODE_COOL = "cool"

CONF_TARGET_VTHERM = "target_vtherm_unique_id"
CONF_START_OFFSET = "start_offset"
CONF_MAX_STEP = "max_step"

#: A negative offset starts gently: the unit sees a small difference with the room.
DEFAULT_START_OFFSET = -0.5
#: Maximum setpoint change per cycle in the direction that increases the demand. 0 means no limit.
DEFAULT_MAX_STEP = 1.0

#: A cycle tick can come a little early: a step is due slightly before a whole cycle.
CYCLE_TOLERANCE_SEC = 5

#: The slope of the room temperature of the thermostat is not used until the ramp has run this many cycles: right after a switch-on
#: it still reflects the room before the heating.
SLOPE_WARMUP_CYCLES = 2

#: Key of the regulation period in the configuration of a VTherm (the core constant is not imported to keep the plugin independent).
CONF_AUTO_REGULATION_PERIOD_MIN = "auto_regulation_periode_min"

#: Recorder can only filter top-level keys, so all the attributes live under one section.
ATTR_GENTLE_START_SECTION = "gentle_start"
