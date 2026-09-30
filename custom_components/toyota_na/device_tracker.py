"""Device tracker platform for Toyota Connected Services"""
import logging
from typing import Any, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaLocation import ToyotaLocation

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN
from .entity_discovery import setup_entity_discovery

_LOGGER = logging.getLogger(__name__)

features_sensors = [
    {"feature": VehicleFeatures.ParkingLocation, "name": "Last Parked Location"},
    {"feature": VehicleFeatures.RealTimeLocation, "name": "Current Location"},
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the device_tracker platform."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    def discover_locations():
        for vehicle in coordinator.data or []:
            for entity_config in features_sensors:
                vehicle_feature = cast(
                    VehicleFeatures, entity_config["feature"]
                )
                feature = vehicle.features.get(vehicle_feature)
                if isinstance(feature, ToyotaLocation):
                    yield ToyotaDeviceTracker(
                        vehicle_feature,
                        coordinator,
                        entity_config["name"],
                        vehicle.vin,
                    )

    setup_entity_discovery(
        config_entry,
        coordinator,
        async_add_devices,
        discover_locations,
    )


class ToyotaDeviceTracker(ToyotaNABaseEntity, TrackerEntity):
    _icon = "mdi:map-marker"
    _vehicle_feature: VehicleFeatures

    def __init__(self, feature: VehicleFeatures, *args: Any):
        super().__init__(*args)
        self._feature = feature

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def latitude(self):
        feat = cast(ToyotaLocation, self.feature(self._feature))
        if feat is not None:
            return feat.lat

    @property
    def longitude(self):
        feat = cast(ToyotaLocation, self.feature(self._feature))
        if feat is not None:
            return feat.value

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def available(self):
        return self.feature(self._feature) is not None
