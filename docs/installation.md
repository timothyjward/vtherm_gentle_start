# Installation

## Requirements

* Home Assistant `2025.8.0` or later.
* Versatile Thermostat `10.6.4` or later. That release calls the regulated temperature modifier of the plugin API ([jmcollin78/versatile_thermostat#2168](https://github.com/jmcollin78/versatile_thermostat/pull/2168)). With an older release the plugin loads but never changes a setpoint.
* `vtherm_api >= 0.8.0`. Home Assistant installs it from the manifest of the plugin.
* At least one `over_climate` thermostat, without direct valve regulation.

## With HACS

The plugin is not in the default HACS store, so add it as a custom repository.

1. Open HACS, open the top-right menu and choose **Custom repositories**.
2. Add `https://github.com/timothyjward/vtherm_gentle_start` with the category **Integration**.
3. Install **Versatile Thermostat Gentle Start** and restart Home Assistant.

HACS installs the latest release. A release is first published as a pre-release, which HACS offers only when **Show beta versions** is enabled on the page of the repository, and it is promoted to a release when it is ready.

To update, use the update entry of HACS and restart Home Assistant. Restart after every update: a new version can add entities, and Home Assistant creates them when the entry is set up.

## By hand

Copy the folder `custom_components/vtherm_gentle_start` of the repository into the `custom_components` folder of Home Assistant and restart.

## Next step

Add the plugin to a thermostat: see [Configuration](configuration.md).

## Removal

1. Delete the **Versatile Thermostat Gentle Start** entry of each thermostat in **Settings, Devices and services**. The thermostat reloads and goes back to sending the regulated temperature as VTherm computes it. The sensor and its device are removed with the entry.
2. Remove the plugin in HACS, or delete the folder `custom_components/vtherm_gentle_start`, and restart Home Assistant.
