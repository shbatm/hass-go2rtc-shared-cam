"""HTTP views for SharedCam — status JSON endpoint and SSE stream."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.event import TrackTemplate, async_track_template_result
from homeassistant.helpers.template import Template

from .const import CONF_SHOW_VIEWERS, CONF_STATUS_TEMPLATE, DOMAIN
from .coordinator import SharedCamCoordinator, _consumer_count

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _find_coordinator(hass: HomeAssistant, camera_name: str) -> SharedCamCoordinator | None:
    """Look up the coordinator for a given camera name via config entry runtime_data."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        coord = getattr(entry, "runtime_data", None)
        if isinstance(coord, SharedCamCoordinator) and coord.camera_name == camera_name:
            return coord
    return None


def _build_status_payload(hass: HomeAssistant, coordinator: SharedCamCoordinator) -> dict:
    """Build the status payload.

    Returns a disabled indicator when the stream is not registered in go2rtc.
    Otherwise returns viewer count plus the rendered status template (if configured).
    """
    if coordinator.data is None:
        return {"available": False, "message": "Stream not available at this time"}

    payload: dict = {"available": True}
    if coordinator.config_entry.options.get(CONF_SHOW_VIEWERS, True):
        payload["viewers"] = _consumer_count(coordinator.data)

    template_str: str | None = coordinator.config_entry.options.get(CONF_STATUS_TEMPLATE)
    if template_str:
        try:
            rendered = Template(template_str, hass).async_render(parse_result=False)
            payload["status"] = rendered.strip()
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to render status template for '%s'", coordinator.camera_name
            )

    return payload


class SharedCamStatusView(HomeAssistantView):
    """GET /api/sharedcam/status/{camera_name} — JSON snapshot."""

    url = "/api/sharedcam/status/{camera_name}"
    name = "api:sharedcam:status"
    requires_auth = True  # Caddy proxy supplies Bearer token

    async def get(self, request: web.Request, camera_name: str) -> web.Response:
        """Return a JSON status payload for the given camera."""
        hass: HomeAssistant = request.app["hass"]
        coordinator = _find_coordinator(hass, camera_name)
        if coordinator is None:
            return web.json_response({"error": "Camera not found"}, status=404)

        return web.json_response(_build_status_payload(hass, coordinator))


class SharedCamEventsView(HomeAssistantView):
    """GET /api/sharedcam/status/{camera_name}/events — SSE stream.

    Pushes an event whenever:
    - The rendered output of the status template changes (tracks all referenced entities)
    - The go2rtc viewer count or stream enabled state changes (coordinator poll, 30 s)
    """

    url = "/api/sharedcam/status/{camera_name}/events"
    name = "api:sharedcam:events"
    requires_auth = True  # Caddy proxy supplies Bearer token

    async def get(self, request: web.Request, camera_name: str) -> web.Response:
        """Open an SSE stream for the given camera."""
        hass: HomeAssistant = request.app["hass"]
        coordinator = _find_coordinator(hass, camera_name)
        if coordinator is None:
            return web.Response(text="Camera not found", status=404)

        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        # Prevent nginx / Caddy from buffering SSE frames
        response.headers["X-Accel-Buffering"] = "no"
        await response.prepare(request)

        # Send initial snapshot immediately so the page doesn't have to wait
        initial = json.dumps(_build_status_payload(hass, coordinator))
        await response.write(f"data: {initial}\n\n".encode())

        change_event = asyncio.Event()

        # --- Status template subscription ---
        # async_track_template_result auto-discovers all entities referenced in the
        # template and fires whenever the rendered output changes.
        template_str: str | None = coordinator.config_entry.options.get(CONF_STATUS_TEMPLATE)

        def _on_template_result(event, updates) -> None:
            change_event.set()

        if template_str:
            result_info = async_track_template_result(
                hass,
                [TrackTemplate(Template(template_str, hass), None)],
                _on_template_result,
            )
            unsub_template = result_info.async_remove
        else:
            def unsub_template() -> None:
                pass  # no status template configured

        # --- Coordinator listener for stream state / viewer count delta ---
        # go2rtc has no push events; coordinator polls every 30 s.
        # Push an SSE event when the stream is enabled/disabled or viewer count changes.
        last_viewer_count: list[int] = [_consumer_count(coordinator.data)]
        last_enabled: list[bool] = [coordinator.data is not None]

        def _on_coordinator_update() -> None:
            new_count = _consumer_count(coordinator.data)
            new_enabled = coordinator.data is not None
            if new_count != last_viewer_count[0] or new_enabled != last_enabled[0]:
                last_viewer_count[0] = new_count
                last_enabled[0] = new_enabled
                change_event.set()

        unsub_coordinator = coordinator.async_add_listener(_on_coordinator_update)

        try:
            while True:
                try:
                    await asyncio.wait_for(change_event.wait(), timeout=15.0)
                    change_event.clear()
                    payload = json.dumps(_build_status_payload(hass, coordinator))
                    await response.write(f"data: {payload}\n\n".encode())
                except asyncio.TimeoutError:  # noqa: PERF203
                    # Keepalive comment — prevents proxy / browser from closing idle connection
                    await response.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
            pass
        finally:
            unsub_template()
            unsub_coordinator()

        return response
