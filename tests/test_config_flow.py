"""Tests for the SharedCam config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sharedcam.const import (
    CONF_CAMERA_NAME,
    CONF_FRIENDLY_NAME,
    CONF_FRIGATE_URL,
    CONF_GO2RTC_URL,
    CONF_SHOW_VIEWERS,
    CONF_STATUS_TEMPLATE,
    DOMAIN,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

VALID_USER_INPUT = {
    CONF_GO2RTC_URL: "http://go2rtc.example.com:1984",
    CONF_FRIGATE_URL: "rtsp://frigate.example.com:8554",
    CONF_CAMERA_NAME: "front_door",
}

VALID_OPTIONS = {
    CONF_SHOW_VIEWERS: True,
    CONF_STATUS_TEMPLATE: "",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_validate_ok():
    """Patch _validate_go2rtc_url to succeed (return None)."""
    with patch(
        "custom_components.sharedcam.config_flow._validate_go2rtc_url",
        return_value=None,
    ):
        yield


@pytest.fixture
def mock_validate_fail():
    """Patch _validate_go2rtc_url to fail (return error key)."""
    with patch(
        "custom_components.sharedcam.config_flow._validate_go2rtc_url",
        return_value="cannot_connect",
    ):
        yield


# ---------------------------------------------------------------------------
# Config flow — user step
# ---------------------------------------------------------------------------


async def test_user_step_shows_form(hass):
    """Initial form is shown with the correct step_id and no errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_cannot_connect_shows_error(hass, mock_validate_fail):
    """go2rtc URL validation failure re-shows the form with cannot_connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_USER_INPUT
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_GO2RTC_URL: "cannot_connect"}


async def test_valid_user_step_advances_to_options(hass, mock_validate_ok):
    """Successful user step advances to the inline options form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_USER_INPUT
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "options"


# ---------------------------------------------------------------------------
# Config flow — full two-step flow
# ---------------------------------------------------------------------------


async def test_full_flow_creates_entry(hass, mock_validate_ok):
    """Completing user + options steps creates an entry with correct data and options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_USER_INPUT
    )
    assert result["step_id"] == "options"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_OPTIONS
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "front_door"
    assert result["data"][CONF_CAMERA_NAME] == "front_door"
    assert result["data"][CONF_GO2RTC_URL] == VALID_USER_INPUT[CONF_GO2RTC_URL]
    assert result["data"][CONF_FRIGATE_URL] == VALID_USER_INPUT[CONF_FRIGATE_URL]
    assert result["options"][CONF_SHOW_VIEWERS] is True


async def test_friendly_name_used_as_title(hass, mock_validate_ok):
    """When a friendly name is provided it becomes the entry title."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**VALID_USER_INPUT, CONF_FRIENDLY_NAME: "Front Door"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_OPTIONS
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front Door"


async def test_camera_name_normalised_to_lowercase(hass, mock_validate_ok):
    """Camera name is stripped and lowercased before being stored."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**VALID_USER_INPUT, CONF_CAMERA_NAME: "  Front_Door  "},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_OPTIONS
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CAMERA_NAME] == "front_door"


async def test_duplicate_camera_aborts(hass, mock_validate_ok):
    """A second flow for the same camera_name aborts with already_configured."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="front_door",
        data=VALID_USER_INPUT,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=VALID_USER_INPUT
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Config flow — Frigate integration present
# ---------------------------------------------------------------------------


async def test_frigate_streams_accepted_in_flow(hass, mock_validate_ok):
    """When Frigate data is present a stream name from Frigate completes the flow."""
    frigate_entry = MockConfigEntry(
        domain="frigate",
        data={"url": "http://frigate.example.com"},
        entry_id="frigate_test_id",
    )
    frigate_entry.add_to_hass(hass)
    hass.data["frigate"] = {
        "frigate_test_id": {
            "config": {
                "go2rtc": {"streams": {"front_door": {}, "back_yard": {}}}
            }
        }
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_GO2RTC_URL: "http://go2rtc.example.com:1984",
            CONF_FRIGATE_URL: "rtsp://frigate.example.com:8554",
            CONF_CAMERA_NAME: "front_door",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "options"


# ---------------------------------------------------------------------------
# Options flow (post-setup Configure button)
# ---------------------------------------------------------------------------


async def test_options_flow_shows_form(hass):
    """Options flow shows the init form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="front_door",
        data=VALID_USER_INPUT,
        options={CONF_SHOW_VIEWERS: True, CONF_STATUS_TEMPLATE: ""},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_saves_values(hass):
    """Options flow persists updated show_viewers and status_template."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="front_door",
        data=VALID_USER_INPUT,
        options={CONF_SHOW_VIEWERS: True, CONF_STATUS_TEMPLATE: ""},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SHOW_VIEWERS: False,
            CONF_STATUS_TEMPLATE: "{{ states('sensor.temp') }}",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SHOW_VIEWERS] is False
    assert result["data"][CONF_STATUS_TEMPLATE] == "{{ states('sensor.temp') }}"
