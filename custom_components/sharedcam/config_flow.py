"""Config flow for SharedCam."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    CONF_CAMERA_NAME,
    CONF_FRIENDLY_NAME,
    CONF_FRIGATE_URL,
    CONF_GO2RTC_URL,
    CONF_SHOW_VIEWERS,
    CONF_STATUS_TEMPLATE,
    DEFAULT_FRIGATE_URL,
    DEFAULT_GO2RTC_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _get_frigate_data(hass) -> tuple[list[str], str | None]:
    """Return (go2rtc stream names, RTSP base URL) from Frigate's loaded config.

    Reads hass.data["frigate"] directly without importing anything from the
    Frigate integration — soft optional dependency that degrades gracefully to
    ([], None) when Frigate is not loaded or has no go2rtc streams.

    The RTSP base URL is derived from Frigate's HTTP API URL using the same
    hostname and the standard Frigate RTSP port 8554 — matching the pattern
    used by Frigate's own camera entities.
    """
    for entry in hass.config_entries.async_entries("frigate"):
        frigate_data = hass.data.get("frigate", {}).get(entry.entry_id, {})
        config = frigate_data.get("config", {})
        streams = config.get("go2rtc", {}).get("streams", {})
        if not streams:
            continue

        rtsp_base: str | None = None
        http_url = entry.data.get("url", "")
        if http_url:
            host = urlparse(http_url).hostname
            if host:
                rtsp_base = f"rtsp://{host}:8554"

        return sorted(streams.keys()), rtsp_base

    return [], None


async def _validate_go2rtc_url(hass, url: str) -> str | None:
    """Try GET /api/streams and return an error key on failure, None on success."""
    try:
        from go2rtc_client import Go2RtcRestClient  # noqa: PLC0415

        session = async_get_clientsession(hass)
        client = Go2RtcRestClient(session, url)
        await client.streams.list()
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("go2rtc validation failed for %s: %s", url, err)
        return "cannot_connect"
    else:
        return None


class SharedCamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SharedCam."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Single-step config flow: go2rtc URL, Frigate URL, camera name, friendly name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            camera_name = user_input[CONF_CAMERA_NAME].strip().lower()
            user_input[CONF_CAMERA_NAME] = camera_name

            # Enforce uniqueness: camera name is the unique ID for this domain.
            # _abort_if_unique_id_configured() raises AbortFlow("already_configured")
            # if another entry with this ID already exists.
            await self.async_set_unique_id(camera_name)
            self._abort_if_unique_id_configured()

            if not errors:
                error_key = await _validate_go2rtc_url(
                    self.hass, user_input[CONF_GO2RTC_URL]
                )
                if error_key:
                    errors[CONF_GO2RTC_URL] = error_key

            if not errors:
                friendly = user_input.get(CONF_FRIENDLY_NAME, "").strip()
                self._validated_config = user_input
                self._entry_title = friendly or camera_name
                return await self.async_step_options()

        # Fetch available Frigate go2rtc streams and derived RTSP base URL.
        frigate_streams, frigate_rtsp_base = _get_frigate_data(self.hass)
        configured_names = {
            e.data[CONF_CAMERA_NAME]
            for e in self.hass.config_entries.async_entries(DOMAIN)
        }
        available_streams = [s for s in frigate_streams if s not in configured_names]

        # camera_name: dropdown when Frigate streams are available, text otherwise.
        if available_streams:
            camera_name_field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=available_streams,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            camera_name_field = str

        # RTSP base URL: pre-populated from Frigate's hostname when available,
        # editable so the user can correct it if their setup differs.
        frigate_url_default = frigate_rtsp_base or DEFAULT_FRIGATE_URL

        schema = vol.Schema(
            {
                vol.Required(CONF_GO2RTC_URL, default=DEFAULT_GO2RTC_URL): str,
                vol.Required(CONF_FRIGATE_URL, default=frigate_url_default): str,
                vol.Required(CONF_CAMERA_NAME): camera_name_field,
                vol.Optional(CONF_FRIENDLY_NAME): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Present options form immediately after the user step."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._entry_title,
                data=self._validated_config,
                options=user_input,
            )

        return self.async_show_form(
            step_id="options",
            data_schema=_OPTIONS_SCHEMA,
        )

    @classmethod
    def async_get_options_flow(
        cls, config_entry: config_entries.ConfigEntry
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return SharedCamOptionsFlow()


_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SHOW_VIEWERS, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_STATUS_TEMPLATE): selector.TemplateSelector(),
    }
)


class SharedCamOptionsFlow(config_entries.OptionsFlow):
    """Options flow for SharedCam — configure the status Jinja2 template.

    No config entry reload is needed: the template is read live from
    entry.options on every /status request and at SSE connection open time.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
