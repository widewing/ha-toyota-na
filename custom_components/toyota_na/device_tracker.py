"""Device tracker platform for Toyota Connected Services"""
import logging
from typing import Any, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaLocation import ToyotaLocation

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN

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
    locations = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for index, vehicle in enumerate(coordinator.data):
        _LOGGER.debug(f"Setting up device trackers for vehicle {vehicle.vin}, features: {list(vehicle.features.keys())}")

        for feature_sensor in features_sensors:
            feature = vehicle.features.get(
                cast(VehicleFeatures, feature_sensor["feature"])
            )

            if feature is not None and isinstance(feature, ToyotaLocation):
                _LOGGER.info(f"Adding device tracker: {feature_sensor['name']} for {vehicle.vin}")
                locations.append(
                    ToyotaDeviceTracker(
                        cast(VehicleFeatures, feature_sensor["feature"]),
                        coordinator,
                        feature_sensor["name"],
                        vehicle,
                        index,
                    )
                )
            else:
                _LOGGER.debug(f"Skipping {feature_sensor['name']} - feature not available or wrong type")

    async_add_devices(locations, True)


class ToyotaDeviceTracker(ToyotaNABaseEntity, TrackerEntity):
    _icon = "mdi:map-marker"
    _vehicle_feature: VehicleFeatures

    def __init__(self, feature: VehicleFeatures, coordinator, name, vehicle: ToyotaVehicle, index: int):
        super().__init__(coordinator, vehicle, index)
        self._feature = feature
        self._attr_name = f"{vehicle.model_name} {name}"
        self._attr_unique_id = f"{vehicle.vin}_{feature.name.lower()}"

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
