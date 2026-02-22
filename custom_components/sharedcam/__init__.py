"""SharedCam — manages a standalone go2rtc instance for sharing camera streams."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .const import CONF_CAMERA_NAME, DOMAIN
from .coordinator import SharedCamCoordinator
from .views import SharedCamEventsView, SharedCamStatusView

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "sensor", "binary_sensor"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Typed config entry alias — runtime_data holds the coordinator for this camera.
SharedCamConfigEntry: TypeAlias = ConfigEntry[SharedCamCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SharedCam component."""
    # hass.data[DOMAIN] is kept only for the one-time HTTP view registration guard.
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SharedCamConfigEntry) -> bool:
    """Set up SharedCam from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SharedCamCoordinator(hass, entry)

    # Initial poll — raises ConfigEntryNotReady if go2rtc is unreachable
    await coordinator.async_config_entry_first_refresh()

    # Re-register the stream if it was enabled before HA restarted.
    # go2rtc has no persistent stream config (go2rtc.yaml has no static streams),
    # so all streams are lost when go2rtc restarts.
    if entry.options.get("stream_enabled") and coordinator.data is None:
        try:
            await coordinator.async_enable_stream()
            await coordinator.async_refresh()
            _LOGGER.info(
                "Re-registered go2rtc stream '%s' after HA restart",
                entry.data[CONF_CAMERA_NAME],
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to re-register stream '%s' after HA restart: %s",
                entry.data[CONF_CAMERA_NAME],
                err,
            )

    # Store coordinator on the entry itself (IQS: runtime-data rule).
    entry.runtime_data = coordinator

    # Register HTTP views once — they are shared across all config entries.
    if "_views_registered" not in hass.data[DOMAIN]:
        hass.http.register_view(SharedCamStatusView())
        hass.http.register_view(SharedCamEventsView())
        hass.data[DOMAIN]["_views_registered"] = True
        _LOGGER.debug("SharedCam HTTP views registered")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SharedCamConfigEntry) -> bool:
    """Unload a config entry."""
    # runtime_data lifecycle is managed by HA; no manual cleanup required.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
