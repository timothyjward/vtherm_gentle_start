# Limitations

## What the plugin does not do

* **It supports `over_climate` thermostats only.** A thermostat which regulates a valve directly, and the other VTherm types, are not offered.
* **It acts in the `heat` and `cool` modes only.**
* **It only delays, holds or lowers the demand.** It never sends a setpoint beyond the regulated temperature of VTherm, so it cannot make a device work harder than VTherm would.
* **It does not switch a device on or off.** The modes, the target and the presets stay under the control of VTherm.
* **It does not check or retry commands.** Each step is a command sent to the device, with no confirmation that the device applied it. A command which fails is handled as VTherm handles it without the plugin. See [Reducing API calls](reducing-api-calls.md) for an automation which makes sure a device switches off.
* **It does not coordinate several devices.** Each thermostat has its own ramp. There is no group behaviour, for example for several indoor units on one outdoor unit.
* **It cannot remove an overshoot caused by a long delay in the heating system.** The slope guard looks one adjustment ahead and makes the device ease off a little earlier.
* **It sends more commands than VTherm alone.** See [Reducing API calls](reducing-api-calls.md).

## Reloading the only thermostat

When Versatile Thermostat `10.6.4` unloads a thermostat entry and no other thermostat entry remains, it removes its API object, and the Gentle Start registration with it. The plugin then stays detached until Home Assistant restarts.

* **Adding or removing the Gentle Start entry** reloads the target thermostat so that it takes the change up at once. With a single Versatile Thermostat entry the reload removes the registration, so after adding an entry the thermostat shows no `gentle_start` attribute and no ramp. Restart Home Assistant after adding the entry.
* **Reloading or reconfiguring the only thermostat** has the same effect, whether or not it has a Gentle Start entry: restart Home Assistant afterwards.
* **With two or more thermostat entries** the API object is kept, so the thermostat takes up the change at once. This follows from the code of `10.6.4`: it removes the API object only when no other entry remains.

## Dependencies

* It needs VTherm `10.6.4` or later and `vtherm_api` `0.8.0` or later. With an older VTherm the plugin loads and does nothing.
* It uses the `temperature_slope` computed by VTherm. When that value is unknown or stale, the slope guard is not applied or is wrong for a while.

## What has been tested

* **Automated tests.** The ramp logic, the manager, the configuration flow, the setup and the sensor are covered by unit tests, which also run against a real Home Assistant core and the VTherm `10.6.4` thermostat in the test environment of the author, for heating and cooling.
* **Heating on real units.** Heating has been tested against real air conditioning units, Daikin heat pumps reached through a cloud integration.
* **Other makes and models.** The plugin has not been tried on other makes and models.
* **Cooling on real units.** Cooling is covered by the automated tests and by the checks against the VTherm thermostat, but it has not been tried on real hardware.
* **Not tested.** Temperatures in Fahrenheit, and thermostats with several underlying devices, have not been exercised on real hardware.

## Responsibility

The plugin is provided under the MIT licence, without warranty. It is not a safety device and does not replace the protections of the device or of VTherm. A device which fails to switch off, whatever the cause, can overheat or overcool a room: use the protections of your installation and, if your device is reached through a cloud service, consider the automation in [Reducing API calls](reducing-api-calls.md).
