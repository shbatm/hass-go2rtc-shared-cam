"""Switch platform for SharedCam — enables/disables a go2rtc stream."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAMERA_NAME, CONF_FRIENDLY_NAME, DOMAIN
from .coordinator import SharedCamCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,  # runtime_data: SharedCamCoordinator
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SharedCam switch from a config entry."""
    async_add_entities([SharedCamSwitch(entry.runtime_data, entry)])


class SharedCamSwitch(CoordinatorEntity[SharedCamCoordinator], SwitchEntity):
    """Switch that enables (PUT /api/streams) or disables (DELETE + restart) a stream."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SharedCamCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        camera_name = entry.data[CONF_CAMERA_NAME]
        friendly = entry.data.get(CONF_FRIENDLY_NAME) or camera_name

        self._attr_unique_id = f"{DOMAIN}_{camera_name}_switch"
        # name=None → display name equals the device name (primary entity of the device)
        self._attr_name = None
        self.entity_id = f"switch.sharedcam_{camera_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=friendly,
            manufacturer="SharedCam",
            model="go2rtc stream",
        )

    @property
    def is_on(self) -> bool:
        """Stream is on when its key is present in /api/streams (coordinator.data is not None)."""
        return self.coordinator.data is not None

    @property
    def icon(self) -> str:
        """Return an icon reflecting stream state."""
        return "mdi:camera-outline" if self.is_on else "mdi:camera-off-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the stream: PUT /api/streams, then immediately reflect new state."""
        try:
            await self.coordinator.async_enable_stream()
        except Exception:
            _LOGGER.exception(
                "Failed to enable stream '%s'", self.coordinator.camera_name
            )
            return

        # Persist enabled state so it survives HA restarts
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, "stream_enabled": True},
        )
        # Optimistic immediate update — don't wait for the 30s poll cycle.
        # Set stream data to an empty (no consumers yet) but present entry.
        self.coordinator.async_set_updated_data({"producers": [], "consumers": []})

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the stream: DELETE /api/streams + POST /api/restart."""
        try:
            await self.coordinator.async_disable_stream()
        except Exception:
            _LOGGER.exception(
                "Failed to disable stream '%s'", self.coordinator.camera_name
            )
            return

        # Persist disabled state
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, "stream_enabled": False},
        )
        # None = stream not registered in go2rtc — immediately reflected across all entities
        self.coordinator.async_set_updated_data(None)
