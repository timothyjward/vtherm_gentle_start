# Changelog

All notable changes of the plugin are listed here, newest first. The version is the tag of the release.

## Unreleased

* Documentation moved to the `docs` folder: installation, configuration, how it works, attributes and sensor, reducing API calls, troubleshooting, limitations and development. The README is now an overview with links.
* The documentation has screenshots taken from a local Home Assistant with Versatile Thermostat `10.6.4`, and the commands sent at a switch-on are counted from measured service calls: four fixed commands with the plugin, three without it.
* Fixed the plugin being lost when the only Versatile Thermostat entry is reloaded. Versatile Thermostat `10.6.4` drops its API object, and the plugin registration with it, when its last entry is unloaded. The plugin now registers again before the thermostat is set up, and reloads a thermostat which comes back without it, so adding the Gentle Start entry or changing the options of a single thermostat no longer needs a restart.

## 0.0.2

* Added the adjustment sensor, on its own device connected to the thermostat. Its state is the ramp setpoint minus the regulated temperature, with a stairs icon which follows the direction of the ramp.
* Added the `ramp_target` attribute to the `gentle_start` section: the regulated temperature the ramp is heading for.

## 0.0.1

First version, published as a pre-release.

* Gentle start of an `over_climate` thermostat: the first setpoint is the room temperature plus a start offset, then the setpoint moves towards the regulated temperature by a limited step per cycle, for heating and for cooling.
* The start setpoint is sent to the device before it is switched on.
* A slope guard, based on the `temperature_slope` of VTherm, holds or lowers the setpoint when the room would pass the target before the next adjustment.
* A ramp in progress resumes after a restart of Home Assistant.
* One configuration entry per thermostat, with the start offset and the maximum step per cycle, which can be changed with **Reconfigure**.
* The `gentle_start` attributes of the thermostat: `start_offset`, `max_step`, `ramp_value` and `action`.
* Installation with HACS as a custom repository, with English and French texts.
