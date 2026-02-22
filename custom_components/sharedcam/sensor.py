"""Sensor platform for SharedCam — active viewer count."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAMERA_NAME, CONF_FRIENDLY_NAME, DOMAIN
from .coordinator import SharedCamCoordinator, _consumer_count

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,  # runtime_data: SharedCamCoordinator
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SharedCam viewer sensor from a config entry."""
    async_add_entities([SharedCamViewersSensor(entry.runtime_data, entry)])


class SharedCamViewersSensor(CoordinatorEntity[SharedCamCoordinator], SensorEntity):
    """Sensor reporting the number of active go2rtc stream consumers."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-eye"
    _attr_native_unit_of_measurement = "viewers"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: SharedCamCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        camera_name = entry.data[CONF_CAMERA_NAME]
        friendly = entry.data.get(CONF_FRIENDLY_NAME) or camera_name

        self._attr_unique_id = f"{DOMAIN}_{camera_name}_viewers"
        self._attr_name = "Viewers"
        self.entity_id = f"sensor.sharedcam_{camera_name}_viewers"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=friendly,
            manufacturer="SharedCam",
            model="go2rtc stream",
        )

    @property
    def native_value(self) -> int:
        """Return the number of active consumers from the latest coordinator data."""
        return _consumer_count(self.coordinator.data)
