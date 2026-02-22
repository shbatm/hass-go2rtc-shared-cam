"""Binary sensor platform for SharedCam — stream registered in go2rtc."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAMERA_NAME, CONF_FRIENDLY_NAME, DOMAIN
from .coordinator import SharedCamCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,  # runtime_data: SharedCamCoordinator
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SharedCam binary sensor from a config entry."""
    async_add_entities([SharedCamEnabledBinarySensor(entry.runtime_data, entry)])


class SharedCamEnabledBinarySensor(
    CoordinatorEntity[SharedCamCoordinator], BinarySensorEntity
):
    """Binary sensor that is ON when the stream key is present in go2rtc /api/streams."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:broadcast"

    def __init__(
        self, coordinator: SharedCamCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        camera_name = entry.data[CONF_CAMERA_NAME]
        friendly = entry.data.get(CONF_FRIENDLY_NAME) or camera_name

        self._attr_unique_id = f"{DOMAIN}_{camera_name}_enabled"
        self._attr_name = "Enabled"
        self.entity_id = f"binary_sensor.sharedcam_{camera_name}_enabled"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=friendly,
            manufacturer="SharedCam",
            model="go2rtc stream",
        )

    @property
    def is_on(self) -> bool:
        """Return True when the stream is registered in go2rtc (coordinator.data is not None)."""
        return self.coordinator.data is not None
