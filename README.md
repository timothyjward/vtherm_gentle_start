<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/vtherm_gentle_start/brand/dark_logo@2x.png">
  <img alt="Gentle Start for Versatile Thermostat" src="custom_components/vtherm_gentle_start/brand/logo@2x.png" width="360">
</picture>

# Versatile Thermostat Gentle Start

`vtherm_gentle_start` is an external plugin for [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm). It lets a device such as an air to air heat pump start gently: instead of receiving the full target setpoint as soon as it is switched on, the device receives a setpoint relative to the room temperature, which then moves towards the target by a limited step per cycle. It also watches how fast the room temperature moves, and stops raising the setpoint when the room would pass the target before the next adjustment.

It applies to `over_climate` VTherms. A direct valve regulation drives the valve opening, not a setpoint, so it is not concerned.

## Example

The room is at 18 degrees and the target is 21 degrees. With the defaults, heating sends 17.5 when it is switched on, then 18.5, 19.5, 20.5 and 21 on the following cycles, one step per cycle. Cooling is the mirror.

## Quick start

* Requirements: Home Assistant `2025.8.0` or later, Versatile Thermostat `10.6.4` or later, and `vtherm_api >= 0.8.0`.
* Install: in HACS, add `https://github.com/timothyjward/vtherm_gentle_start` as a custom repository of the category **Integration**, install **Versatile Thermostat Gentle Start**, and restart Home Assistant. If HACS shows no version, enable **Show beta versions**.
* Configure: add the **Versatile Thermostat Gentle Start** integration, pick an `over_climate` thermostat, and keep the defaults (start offset -0.5, maximum step 1.0).
* Check: the thermostat shows a `gentle_start` attribute, and a sensor shows how far the ramp is holding the setpoint back.

## Documentation

| Page | Content |
| --- | --- |
| [Installation](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/installation.md) | Requirements, HACS and manual installation, removal. |
| [Configuration](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/configuration.md) | The options and how to choose them. |
| [How it works](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/how-it-works.md) | The ramp, the slope guard and the work with the regulation of VTherm. |
| [Attributes and sensor](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/attributes-and-sensor.md) | The `gentle_start` attributes, the adjustment sensor and a dashboard badge. |
| [Reducing API calls](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/reducing-api-calls.md) | Commands per switch-on, how to send fewer, and an automation which makes sure a device switches off. |
| [Troubleshooting](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/troubleshooting.md) | Checking that the plugin is active, common problems, the debug log. |
| [Limitations](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/limitations.md) | What the plugin does not do, and what has been tested. |
| [Development](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/development.md) | Tests, brand images and releases. |

The [changelog](https://github.com/timothyjward/vtherm_gentle_start/blob/main/CHANGELOG.md) lists what changed in each release.

## Support

Report a problem or ask a question in the [issues](https://github.com/timothyjward/vtherm_gentle_start/issues). The [troubleshooting page](https://github.com/timothyjward/vtherm_gentle_start/blob/main/docs/troubleshooting.md) says what to include.

## License

MIT, see [LICENSE](LICENSE).
