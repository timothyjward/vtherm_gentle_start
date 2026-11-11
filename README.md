<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/vtherm_gentle_start/brand/dark_logo@2x.png">
  <img alt="Gentle Start for Versatile Thermostat" src="custom_components/vtherm_gentle_start/brand/logo@2x.png" width="360">
</picture>

# Versatile Thermostat Gentle Start

`vtherm_gentle_start` is an external plugin for [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm). It lets a device such as an air to air heat pump start gently: instead of receiving the full target setpoint as soon as it is switched on, the device receives a setpoint relative to the room temperature, which then moves towards the target by a limited step per cycle. It also watches how fast the room temperature moves, and stops raising the setpoint when the room would pass the target before the next adjustment.

It applies to `over_climate` VTherms. A direct valve regulation drives the valve opening, not a setpoint, so it is not concerned.

## Requirements

* Home Assistant `2025.8.0` or later.
* Versatile Thermostat `10.6.4` or later: that release calls the regulated temperature modifier of the plugin API ([jmcollin78/versatile_thermostat#2168](https://github.com/jmcollin78/versatile_thermostat/pull/2168)).
* `vtherm_api >= 0.8.0`.

## Installation

This plugin is not in the default HACS store, so add it as a custom repository.

1. Open HACS, open the top-right menu and choose **Custom repositories**.
2. Add `https://github.com/timothyjward/vtherm_gentle_start` with the category **Integration**.
3. Install **Versatile Thermostat Gentle Start** and restart Home Assistant.

To install it manually, copy `custom_components/vtherm_gentle_start` into the `custom_components` folder of Home Assistant and restart.

## Configuration

Add the **Versatile Thermostat Gentle Start** integration from **Settings, Devices and services**, pick the `over_climate` VTherm and set the two options. One entry is created per thermostat, and a thermostat without an entry is not ramped and shows no extra attribute. Adding or deleting an entry reloads that thermostat, so that it takes the change up at once, and nothing else needs a restart. The options can be changed later with **Reconfigure**, without reloading anything.

| Option | Default | Meaning |
| --- | --- | --- |
| Start offset | -0.5 | When the thermostat is switched on, the first setpoint sent is the room temperature plus the offset when heating, minus the offset when cooling, never beyond the target. A negative value gives a gentler start, where the device sees a small difference. A positive value gives a stronger start. |
| Maximum step per cycle | 1.0 | Maximum change of the setpoint per cycle, in degrees, in the direction that increases the demand: upwards when heating, downwards when cooling. A lower target is sent at once. 0 means no limit. |

## Behaviour

The room is at 18 degrees and the target is 21 degrees. With the defaults, heating sends 17.5 when it is switched on, then 18.5, 19.5, 20.5 and 21 on the following cycles, one step per cycle. With a start offset of 1.0 and a step of 0.5 it sends 19, 19.5, 20, 20.5 and 21. Cooling is the mirror: the room is at 26 degrees, the target is 23 degrees, and with the defaults it sends 26.5, 25.5, 24.5, 23.5 and 23.

* When the device is off, the start setpoint is sent to it before it is switched on, so that the device does not start from its own stored setpoint. This is a command sent to the device, not a confirmation that the device applied it.
* The ramp starts again each time the thermostat is switched on (the plugin watches the state of the thermostat, so a quick off and on is seen too), and when it changes between heat and cool. It is not restarted when the device only goes idle. A ramp in progress resumes after a restart of Home Assistant.
* A change made on the device itself, which VTherm follows, is not ramped.
* A cycle is the cycle duration of the thermostat. The maximum step is never lower than the regulation step of the thermostat (the regulation delta, or the target temperature step if it is 0), because the rounding would otherwise cancel each change. A warning is logged when the step is raised.

### Following the room temperature

The plugin uses the slope of the room temperature which VTherm already computes from the sensor, the `temperature_slope` attribute of the thermostat, in degrees per hour. It does not measure anything itself. VTherm updates it at each reading of the sensor, and when the sensor is silent for 30 minutes it adds a flat point, so a sensor which only reports changes can leave a slope in place for a while. The slope is not used during the first two cycles of a ramp, because right after a switch-on it still describes the room before the heating. When it is unknown the ramp is the plain ramp above.

At each step, one per cycle, it predicts the room temperature at the next adjustment: the temperature now plus the slope times the time to the next adjustment, which is the cycle, or the regulation period of the thermostat if it is longer. The limit is the target temperature of the thermostat, not the regulated setpoint, which the self-regulation can set higher.

* The room is not predicted to pass the target: the setpoint rises by one step, as above.
* The room is predicted to pass the target by less than one regulation step: the setpoint is held where it is.
* The room is predicted to pass the target by one regulation step or more: the setpoint is lowered by one step, or by one regulation step when there is no limit per cycle. It never goes below the gentlest level, which is the room temperature plus the start offset when the offset is negative, and the room temperature otherwise.

When the prediction is back under the target, the setpoint rises again by one step per cycle. In cool mode everything is inverted around the room temperature: the start setpoint with a negative offset is above the room, the setpoint goes down towards the target, never below the regulated temperature, and a room which falls fast towards the target gets a higher setpoint, never above the room temperature minus the offset when the offset is negative, which is above the room (the room temperature otherwise). For example with a target of 23 and the defaults, a room at 23 which falls by one degree per cycle gets 23.5 instead of 23. The prediction looks one adjustment ahead, so it cannot cancel an overshoot which comes from a long delay in the heating system. It makes the device ease off a little earlier than it would, it does not remove such an overshoot.

### Working with the regulation of VTherm

* The plugin adjusts the regulated temperature after the self-regulation, and never competes with it. It never sends more than the regulated temperature: it can only delay the rise of the setpoint, hold it or lower it, and a regulated temperature which goes down is sent at once.
* The regulation period, the regulation delta and the cycle of the thermostat keep their usual effect on the adjusted setpoint. A held setpoint is the one last sent, so VTherm sends nothing: holding costs no command.
* A change made on the device itself is followed by VTherm as before, and is not adjusted.

### Commands sent to the device

Each step is a command sent to the device. Switching on sends three commands (the start setpoint, the mode and the start setpoint again), and each following cycle which moves the setpoint sends one more until the target is reached. With the default values and a room 3 degrees below the target this is about seven commands per switch-on and per device, against two without the ramp. If the device is reached through a cloud service which limits the number of requests per minute or per day, increase the maximum step, or add the plugin only to the thermostats which need it.

## Exposed attributes

The thermostat shows a `gentle_start` section:

* `start_offset` and `max_step`: the options.
* `ramp_value`: the setpoint the ramp currently sends, empty when no ramp is in progress.
* `ramp_target`: the regulated temperature the ramp is heading for, empty when no ramp is in progress. The `regulated_target_temperature` attribute of the thermostat itself shows the adjusted setpoint, which is the same as `ramp_value`, so it cannot be used for this.
* `action`: what the ramp did at its last step: `start`, `up`, `reached` (the setpoint is the regulated temperature), `hold` or `down` (the demand was lowered: the setpoint went down when heating, and up when cooling).

## Adjustment sensor

Each entry also creates a sensor, named after the thermostat (for example `Master bedroom gentle start adjustment`). Home Assistant keeps one device per integration entry, so the sensor is on its own device, `<thermostat> Gentle Start`, which is shown as connected to the thermostat. Its state is `ramp_value` minus `ramp_target`, in degrees: how far the ramp is holding the setpoint back. It is `0.0` when no ramp is in progress or when the ramp has reached the regulated temperature, and unknown when the thermostat is unavailable. The `action` attribute repeats the last step of the ramp.

* Heating: the value is negative while the setpoint rises towards the regulated temperature, and the icon is `mdi:stairs-up`.
* Cooling: the value is positive while the setpoint falls towards the regulated temperature, and the icon is `mdi:stairs-down`.
* No adjustment: the icon is `mdi:stairs`.

To show it on a dashboard only while the ramp is adjusting, add it as a badge of a heading card, hidden when it is `0.0` (replace the entity id with the one of your sensor, for example `sensor.master_bedroom_gentle_start_adjustment` for a thermostat named "Master bedroom"):

```yaml
type: heading
heading: Master bedroom
badges:
  - type: entity
    entity: sensor.master_bedroom_gentle_start_adjustment
    visibility:
      - condition: state
        entity: sensor.master_bedroom_gentle_start_adjustment
        state_not:
          - "0.0"
          - unknown
          - unavailable
```

## Development

The tests load the integration of the repository, which depends on Versatile Thermostat: put a checkout of it on the path.

```bash
python -m pip install -r requirements_test.txt
git clone https://github.com/jmcollin78/versatile_thermostat ../versatile_thermostat
PYTHONPATH=.:../versatile_thermostat pytest
```

The brand images in `custom_components/vtherm_gentle_start/brand` are rendered from the SVG sources in `assets/brand`. After changing a source, run `scripts/build_brand.sh` (it needs `rsvg-convert`) and commit the images. Home Assistant uses these images from version 2026.3.

A release is made by pushing a tag such as `0.1.0`: the `Release` workflow sets the version of the manifest from the tag and attaches the zip which HACS installs. The release is published as a pre-release: edit it on GitHub to untick "Set as a pre-release" when it is ready.

## License

MIT, see [LICENSE](LICENSE).
