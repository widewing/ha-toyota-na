from typing import Any, Union, cast
import logging

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import BINARY_SENSORS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the binary_sensor platform."""
    binary_sensors = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        for feature_sensor in BINARY_SENSORS:

            entity_config = feature_sensor

            if entity_config:
                if vehicle.electric is False and cast(bool, entity_config["electric"]):
                    continue
                if vehicle.subscribed is False and cast(bool, entity_config["subscription"]):
                    continue
                binary_sensors.append(
                    ToyotaBinarySensor(
                        cast(VehicleFeatures, feature_sensor["feature"]),
                        cast(str, entity_config["icon"]),
                        cast(BinarySensorDeviceClass, entity_config["device_class"]),
                        coordinator,
                        entity_config["name"],
                        vehicle.vin,
                    )
                )

    async_add_devices(binary_sensors, True)


class ToyotaBinarySensor(ToyotaNABaseEntity, BinarySensorEntity):
    _device_class: Union[BinarySensorDeviceClass, str]
    _vehicle_feature: VehicleFeatures
    _icon: str

    def __init__(
        self,
        vehicle_feature: VehicleFeatures,
        icon: str,
        device_class: Union[BinarySensorDeviceClass, str],
        *args: Any,
    ):
        super().__init__(*args)
        self._icon = icon
        self._device_class = device_class
        self._vehicle_feature = vehicle_feature

    @property
    def device_class(self):
        return self._device_class

    @property
    def icon(self):
        return self._icon

    @property
    def is_on(self):
        sensor = self.feature(self._vehicle_feature)

        if isinstance(sensor, ToyotaLockableOpening):
            if self.device_class == BinarySensorDeviceClass.LOCK:
                return not sensor.locked
            elif self.device_class == BinarySensorDeviceClass.DOOR:
                return not sensor.closed
        elif isinstance(sensor, ToyotaOpening):
            return not sensor.closed
        elif isinstance(sensor, ToyotaRemoteStart):
            if self.device_class == BinarySensorDeviceClass.RUNNING:
                return sensor.on

    @property
    def extra_state_attributes(self):
        if self._vehicle_feature == VehicleFeatures.RemoteStartStatus:
            remote_start = cast(
                ToyotaRemoteStart,
                self.feature(self._vehicle_feature),
            )
            if (
                remote_start is not None
                and remote_start.time_left is not None
                and remote_start.start_time is not None
            ):

                return {
                    "end_time": remote_start.end_time,
                    "minutes_remaining": remote_start.time_left,
                    "start_time": remote_start.start_time,
                    "total_runtime": remote_start.timer,
                }

    @property
    def available(self):
        return self.feature(self._vehicle_feature) is not None
