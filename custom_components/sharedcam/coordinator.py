"""DataUpdateCoordinator for SharedCam."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CAMERA_NAME,
    CONF_FRIGATE_URL,
    CONF_GO2RTC_URL,
    DOMAIN,
    SCAN_INTERVAL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _consumer_count(stream_data) -> int:
    """Return active viewer count from stream data.

    go2rtc returns "consumers": null (not absent) when no viewers are connected,
    so we must guard against None from both the key being absent and being null.
    """
    if stream_data is None:
        return 0
    if isinstance(stream_data, dict):
        return len(stream_data.get("consumers") or [])
    return len(getattr(stream_data, "consumers", None) or [])


class SharedCamCoordinator(DataUpdateCoordinator):
    """Coordinator that polls go2rtc /api/streams for one camera every 30 s."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.config_entry = config_entry
        self.camera_name: str = config_entry.data[CONF_CAMERA_NAME]
        self.go2rtc_url: str = config_entry.data[CONF_GO2RTC_URL]
        self.rtsp_url: str = (
            f"{config_entry.data[CONF_FRIGATE_URL]}/{self.camera_name}"
        )
        self._client = None

    def _get_client(self):
        """Return (and lazily create) the go2rtc REST client."""
        if self._client is None:
            # go2rtc-client v0.4.0 — same library used by HA core go2rtc integration
            from go2rtc_client import Go2RtcRestClient  # noqa: PLC0415

            session = async_get_clientsession(self.hass)
            self._client = Go2RtcRestClient(session, self.go2rtc_url)
        return self._client

    async def _async_update_data(self):
        """Fetch raw stream data for this camera from go2rtc.

        We use the underlying _BaseClient.request() directly so the raw JSON is
        returned — the typed Stream model omits the consumers[] array that we need
        for the viewer count.
        """
        try:
            client = self._get_client()
            resp = await client._client.request("GET", "/api/streams")  # noqa: SLF001
            raw: dict = await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error fetching go2rtc streams: {err}") from err  # noqa: TRY003

        # Returns the per-camera dict {"producers": [...], "consumers": [...]}
        # or None when the stream is not registered.
        return raw.get(self.camera_name)

    # ------------------------------------------------------------------
    # Stream management helpers (called by the switch entity)
    # ------------------------------------------------------------------

    async def async_enable_stream(self) -> None:
        """Register the stream in go2rtc (PUT /api/streams)."""
        await self._get_client().streams.add(self.camera_name, self.rtsp_url)
        _LOGGER.debug("Enabled go2rtc stream '%s' → %s", self.camera_name, self.rtsp_url)

    async def async_disable_stream(self) -> None:
        """Deregister the stream and restart go2rtc (DELETE + POST /api/restart).

        DELETE removes the stream definition but does **not** kick active WebSocket
        consumers — the restart is required to disconnect them immediately.

        Neither streams.delete() nor client.restart() exist in go2rtc-client v0.4.0,
        so we call the underlying _BaseClient.request() directly.
        """
        client = self._get_client()
        # go2rtc DELETE uses ?src=<stream_name> (not the RTSP URL, despite the param name)
        await client._client.request(  # noqa: SLF001
            "DELETE", "/api/streams", params={"src": self.camera_name}
        )
        await client._client.request("POST", "/api/restart")  # noqa: SLF001
        _LOGGER.debug("Disabled go2rtc stream '%s'", self.camera_name)
