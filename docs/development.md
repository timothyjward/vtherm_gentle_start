# Development

## Layout

| Path | Content |
| --- | --- |
| `custom_components/vtherm_gentle_start/ramp.py` | The ramp: pure Python with no Home Assistant dependency, so that it can be tested in isolation. |
| `custom_components/vtherm_gentle_start/manager.py` | The feature manager: connects the ramp to VTherm through the plugin API and publishes the attributes. |
| `custom_components/vtherm_gentle_start/factory.py` | Decides which thermostats the plugin supports. |
| `custom_components/vtherm_gentle_start/sensor.py` | The adjustment sensor. |
| `custom_components/vtherm_gentle_start/config_flow.py` | The configuration and reconfiguration flows. |
| `custom_components/vtherm_gentle_start/__init__.py` | Registers the factory and reloads the target thermostat when an entry is added or removed. |
| `custom_components/vtherm_gentle_start/brand/` | The brand images used by Home Assistant. |
| `assets/brand/` | The SVG sources of the brand images. |
| `tests/` | The tests. |
| `docs/` | This documentation. |

## Tests

The tests load the integration of the repository, which depends on Versatile Thermostat: put a checkout of it on the path. Python 3.13 or later is required.

```bash
python -m pip install -r requirements_test.txt
git clone https://github.com/jmcollin78/versatile_thermostat ../versatile_thermostat
PYTHONPATH=.:../versatile_thermostat pytest
```

The workflow `Tests` does the same on every push to `main` and on every pull request.

## Checks

The workflow `Validate` runs the Home Assistant `hassfest` check and the HACS validation on every push and pull request, and daily. Both must pass before a release.

## Brand images

The brand images in `custom_components/vtherm_gentle_start/brand` are rendered from the SVG sources in `assets/brand`. After changing a source, run `scripts/build_brand.sh` (it needs `rsvg-convert`) and commit the images. Home Assistant uses these images from version 2026.3.

## Releases

A release is made by pushing a tag such as `0.1.0`. The `Release` workflow:

1. sets the version of the manifest from the tag;
2. builds `vtherm_gentle_start.zip` from the integration folder, which is the file HACS installs because `hacs.json` sets `zip_release`;
3. publishes a GitHub release with generated notes.

The release is published as a pre-release. When it is ready, edit it on GitHub and untick **Set as a pre-release**. Update [the changelog](../CHANGELOG.md) before tagging.

## Documentation

* The pages are in `docs/` and are linked from the README and from `docs/README.md`.
* The README uses absolute links to the pages, because HACS shows it inside Home Assistant, where relative links do not work.
* Keep the text in plain ASCII punctuation, with no emoji.
* When the behaviour, an option or an attribute changes, update the matching page: [How it works](how-it-works.md), [Configuration](configuration.md) or [Attributes and sensor](attributes-and-sensor.md).
