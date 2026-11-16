# Troubleshooting

## How to check that the plugin is active

1. Open **Developer tools, States** and select the thermostat.
2. Look for the `gentle_start` attribute. If it is there, the thermostat has the plugin.
3. Switch the thermostat on in `heat` or `cool` mode. At the first regulation, `ramp_value` is the start setpoint and `action` is `start`. On the following cycles `ramp_value` moves towards `ramp_target` and `action` is `up`, then `reached`.
4. The adjustment sensor shows the difference between the two. See [Attributes and sensor](attributes-and-sensor.md).

## The `gentle_start` attribute is missing

* There is no entry for this thermostat. Add the integration and pick it ([Configuration](configuration.md)).
* The thermostat is not an `over_climate`, or it regulates a valve directly. The plugin does not support it, and the entry cannot target it.
* Home Assistant has not been restarted since the plugin was installed. Restart it.
* The entry was added while the thermostat was not loaded. Reload the thermostat, or restart Home Assistant.
* The thermostat is your only Versatile Thermostat entry. Reloading it removes the plugin until Home Assistant restarts, so restart after adding the entry ([Limitations](limitations.md)). A restart is also the check: if the attribute is there afterwards, the plugin was only detached.

## `ramp_value` stays empty

* The thermostat is off, or in a mode other than `heat` or `cool`. The ramp applies only to those two modes.
* The room temperature is unknown: the ramp has nothing to start from, so VTherm sends its setpoint unchanged.
* The VTherm version is older than `10.6.4`. Only that release calls the plugin to adjust the setpoint.
* The thermostat was switched off. The ramp is forgotten at once and starts again at the next switch-on. A ramp which has reached the regulated temperature keeps its value, with `action` set to `reached`, for as long as the thermostat heats or cools.

## The device gets the target at once

* The start offset is large enough, or the room is close enough to the target, for the start setpoint to be the target.
* The maximum step is 0, so the second setpoint is the target.
* The change comes from the device: a change made on the device and followed by VTherm is not ramped.

## The setpoint does not move

`action` is `hold`. The slope of the room temperature predicts that the room would pass the target before the next adjustment, so the setpoint is held. This is expected near the target and is the guard doing its job. See [How it works](how-it-works.md).

If the setpoint stays held while the room is far from the target, check the `temperature_slope` attribute of the thermostat: a sensor which only reports changes can leave a stale slope in place.

## The log says the maximum step was raised

The maximum step is lower than the regulation step of the thermostat, so the regulation step is used instead. Increase the maximum step, or lower the regulation delta. The warning is logged once.

## The sensor is unknown

* The thermostat is unavailable or unknown.
* The entity of the thermostat was renamed or removed. The sensor follows a rename; after a removal it is unknown until the thermostat returns.
* The thermostat has not published `ramp_target` yet. After an update of the plugin, restart Home Assistant so that the thermostat reloads and publishes it.

## The badge does not hide itself

The `visibility` option of heading badges depends on the version of the Home Assistant frontend. Update Home Assistant, or remove the `visibility` block.

## The quota of the device service is used up

See [Reducing API calls](reducing-api-calls.md).

## Enabling the debug log

Add this to `configuration.yaml` and restart, or call the `logger.set_level` service:

```yaml
logger:
  logs:
    custom_components.vtherm_gentle_start: debug
```

The plugin logs when it resets a ramp, when it restores one after a restart, when it reloads a thermostat, and when the maximum step is raised. The decisions of VTherm itself are logged by `custom_components.versatile_thermostat`.

When you report an issue, include the version of the plugin, of VTherm and of Home Assistant, the `gentle_start` attributes of the thermostat, and the debug log around a switch-on.
