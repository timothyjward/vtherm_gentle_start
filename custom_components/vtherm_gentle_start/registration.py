"""Keep the Gentle Start factory registered with Versatile Thermostat.

Versatile Thermostat keeps the factories of the plugins in its API object, and drops that object when the last of its
entries is unloaded. A thermostat which is the only entry of Versatile Thermostat therefore loses the plugin each time it
is reloaded, whether the plugin or the user reloads it. The registration is restored in two ways:

* when the plugin reloads that thermostat, it unloads it, registers the factory with a new API object, and sets it up again;
* when something else reloads it, the watcher sees the thermostat loaded without the factory and reloads it the same way.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from vtherm_api.const import VTHERM_API_NAME
from vtherm_api.log_collector import get_vtherm_logger
from vtherm_api.vtherm_api import VThermAPI

from .const import CONF_TARGET_VTHERM, DOMAIN, FEATURE_MANAGER_GENTLE_START, VT_DOMAIN

_LOGGER = get_vtherm_logger(__name__)

#: The class of the API object of Versatile Thermostat, kept to build the next one: a base API object would not do.
DATA_API_CLASS = "api_class"
#: The stop functions of the state listeners, by id of the thermostat entry.
DATA_WATCHED = "watched"
#: The thermostat entries which were reloaded to restore the factory, and which have not shown it back yet.
DATA_RESTORING = "restoring"


def _data(hass: HomeAssistant) -> dict:
    """The data of the plugin."""
    return hass.data.setdefault(DOMAIN, {})


def current_api(hass: HomeAssistant):
    """The API object of Versatile Thermostat, None when it does not exist.

    It is never created here: Versatile Thermostat creates it with its own class, and an object of another class would break it.
    """
    domain = hass.data.get(VT_DOMAIN)
    return domain.get(VTHERM_API_NAME) if isinstance(domain, dict) else None


def register_factory(hass: HomeAssistant) -> bool:
    """Register the Gentle Start factory with the API object of Versatile Thermostat, which is created when it does not exist."""
    # Imported here: the factory module imports this one
    from .factory import GentleStartManagerFactory  # pylint: disable=import-outside-toplevel

    api = current_api(hass)
    if api is None:
        # The same call Versatile Thermostat makes when it sets an entry up, with its class when it has been seen
        api = _data(hass).get(DATA_API_CLASS, VThermAPI).get_vtherm_api(hass)
    if api is None:
        _LOGGER.warning("Unable to register the Gentle Start factory because VThermAPI is unavailable")
        return False

    _data(hass)[DATA_API_CLASS] = type(api)
    factory = GentleStartManagerFactory()
    if api.get_feature_manager(factory.name) is None:
        api.register_feature_manager(factory)
    return True


def unregister_factory(hass: HomeAssistant) -> None:
    """Unregister the Gentle Start factory."""
    api = current_api(hass)
    if api is not None:
        api.unregister_feature_manager(FEATURE_MANAGER_GENTLE_START)


def is_registered(hass: HomeAssistant) -> bool:
    """True when the factory is registered with the API object of Versatile Thermostat."""
    api = current_api(hass)
    return api is not None and api.get_feature_manager(FEATURE_MANAGER_GENTLE_START) is not None


def _other_thermostat_loaded(hass: HomeAssistant, entry_id: str) -> bool:
    """True when another entry of Versatile Thermostat is loaded, so that the API object survives the unload of this one."""
    return any(entry.entry_id != entry_id and entry.state == ConfigEntryState.LOADED for entry in hass.config_entries.async_entries(VT_DOMAIN))


def _register_while_in_use(hass: HomeAssistant) -> None:
    """Register the factory when an entry of the plugin exists: when none is left, the thermostat has to come back without it."""
    if hass.config_entries.async_entries(DOMAIN):
        register_factory(hass)


async def reload_thermostat(hass: HomeAssistant, entry_id: str) -> None:
    """Reload a thermostat so that it creates (or drops) its manager, and keep the factory registered while it is reloaded."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.state != ConfigEntryState.LOADED:
        return
    _register_while_in_use(hass)
    if _other_thermostat_loaded(hass, entry_id):
        await hass.config_entries.async_reload(entry_id)
        return

    # The API object goes with the unload of the only entry: register again before the entry is set up
    if not await hass.config_entries.async_unload(entry_id):
        return
    try:
        _register_while_in_use(hass)
    finally:
        await hass.config_entries.async_setup(entry_id)


def _is_targeted(hass: HomeAssistant, entry_id: str) -> bool:
    """True when an entry of the plugin targets the thermostat."""
    return any(entry.data.get(CONF_TARGET_VTHERM) == entry_id for entry in hass.config_entries.async_entries(DOMAIN))


def watch(hass: HomeAssistant, entry: ConfigEntry | None) -> None:
    """Watch the state of a thermostat entry, to restore the factory when the thermostat is reloaded without it."""
    watched = _data(hass).setdefault(DATA_WATCHED, {})
    if entry is None or entry.entry_id in watched:
        return

    @callback
    def _on_state_change() -> None:
        if entry.state != ConfigEntryState.LOADED:
            return
        restoring = _data(hass).setdefault(DATA_RESTORING, set())
        if is_registered(hass):
            restoring.discard(entry.entry_id)
            return
        if not _is_targeted(hass, entry.entry_id) or entry.entry_id in restoring:
            # Once only: when the factory is still missing after the reload, reloading again would not help
            if entry.entry_id in restoring:
                _LOGGER.warning("The Gentle Start factory is not registered with %s after it was reloaded: restart Home Assistant", entry.title)
            return
        _LOGGER.debug("The thermostat %s was loaded without the Gentle Start factory: reloading it", entry.title)
        restoring.add(entry.entry_id)
        hass.async_create_task(reload_thermostat(hass, entry.entry_id))

    watched[entry.entry_id] = entry.async_on_state_change(_on_state_change)


def watch_all(hass: HomeAssistant) -> None:
    """Watch every thermostat entry which exists."""
    for entry in hass.config_entries.async_entries(VT_DOMAIN):
        watch(hass, entry)


def unwatch_all(hass: HomeAssistant) -> None:
    """Stop watching the thermostat entries."""
    watched = _data(hass).get(DATA_WATCHED, {})
    while watched:
        _, stop = watched.popitem()
        try:
            stop()
        except ValueError:
            # The listener is not there any more, which is the same
            pass
    _data(hass).pop(DATA_RESTORING, None)
