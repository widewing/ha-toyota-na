"""Device tracker platform for Toyota Connected Services"""
import logging

from homeassistant.components.device_tracker import SOURCE_TYPE_GPS
from homeassistant.components.device_tracker.config_entry import TrackerEntity

from .const import DOMAIN
from .base_entity import ToyotaNABaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the Toyota Connected Services tracker from config entry."""
    trackers = []

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    for vin, vehicle in coordinator.data.items():
        tracker = ToyotaNAParkingTracker(coordinator, vin, "parking location")
        if tracker.available:
            trackers.append(tracker)
        tracker = ToyotaNALocationTracker(coordinator, vin, "realtime location")
        if tracker.available:
            trackers.append(tracker)

    async_add_devices(trackers, True)


class ToyotaNAParkingTracker(ToyotaNABaseEntity, TrackerEntity):
    _attr_icon = "mdi:map-marker"

    @property
    def latitude(self):
        return self.vehicle_status["latitude"]

    @property
    def longitude(self):
        return self.vehicle_status["longitude"]

    @property
    def source_type(self):
        return SOURCE_TYPE_GPS

    @property
    def available(self):
        return "latitude" in self.vehicle_status


class ToyotaNALocationTracker(ToyotaNABaseEntity, TrackerEntity):
    _attr_icon = "mdi:map-marker"

    @property
    def latitude(self):
        return self.vehicle_odometer_detail["vehicleLocation"]["latitude"]

    @property
    def longitude(self):
        return self.vehicle_odometer_detail["vehicleLocation"]["longitude"]

    @property
    def source_type(self):
        return SOURCE_TYPE_GPS

    @property
    def available(self):
        return "vehicleLocation" in self.vehicle_odometer_detail
