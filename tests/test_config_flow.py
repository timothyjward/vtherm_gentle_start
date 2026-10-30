"""Tests for the config flow of vtherm_gentle_start."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vtherm_gentle_start.const import (
    CONF_MAX_STEP,
    CONF_START_OFFSET,
    CONF_TARGET_VTHERM,
    DEFAULT_MAX_STEP,
    DEFAULT_START_OFFSET,
    DOMAIN,
    VT_DOMAIN,
)

OPTIONS = {CONF_START_OFFSET: 0.5, CONF_MAX_STEP: 2.0}


@pytest.fixture(name="vtherm_entity")
def vtherm_entity_fixture(hass: HomeAssistant) -> str:
    """Register a Versatile Thermostat climate entity and return its entity id."""
    entry = er.async_get(hass).async_get_or_create("climate", VT_DOMAIN, "vt-living", suggested_object_id="living_room")
    return entry.entity_id


@pytest.fixture(autouse=True)
def skip_setup_entry():
    """The flow tests do not need the entry to be set up."""
    with patch("custom_components.vtherm_gentle_start.async_setup_entry", return_value=True):
        yield


async def test_user_flow_creates_an_entry(hass: HomeAssistant, vtherm_entity: str) -> None:
    """The user picks a thermostat and the two options, and the entry stores the thermostat unique id."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TARGET_VTHERM: vtherm_entity, **OPTIONS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_TARGET_VTHERM: "vt-living", **OPTIONS}


async def test_user_flow_defaults(hass: HomeAssistant, vtherm_entity: str) -> None:
    """The options default to a start offset of -0.5 and a maximum step of 1.0."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TARGET_VTHERM: vtherm_entity})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_START_OFFSET] == DEFAULT_START_OFFSET
    assert result["data"][CONF_MAX_STEP] == DEFAULT_MAX_STEP


async def test_user_flow_rejects_an_unknown_entity(hass: HomeAssistant) -> None:
    """An entity which is not in the registry is refused."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TARGET_VTHERM: "climate.unknown", **OPTIONS})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_TARGET_VTHERM: "invalid_entity"}


async def test_user_flow_rejects_a_negative_step(hass: HomeAssistant, vtherm_entity: str) -> None:
    """The maximum step cannot be negative."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TARGET_VTHERM: vtherm_entity, CONF_START_OFFSET: -0.5, CONF_MAX_STEP: -1.0})


async def test_user_flow_aborts_when_already_configured(hass: HomeAssistant, vtherm_entity: str) -> None:
    """A thermostat gets one entry only."""
    MockConfigEntry(domain=DOMAIN, unique_id=f"{DOMAIN}-vt-living", data={CONF_TARGET_VTHERM: "vt-living", **OPTIONS}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TARGET_VTHERM: vtherm_entity, **OPTIONS})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_the_options(hass: HomeAssistant) -> None:
    """The reconfigure step edits the two options and keeps the target."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"{DOMAIN}-vt-living", data={CONF_TARGET_VTHERM: "vt-living", **OPTIONS})
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_START_OFFSET: -1.0, CONF_MAX_STEP: 0.5})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_TARGET_VTHERM: "vt-living", CONF_START_OFFSET: -1.0, CONF_MAX_STEP: 0.5}
