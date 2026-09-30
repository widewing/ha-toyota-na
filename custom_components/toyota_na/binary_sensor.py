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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity, vehicle_entity_unique_id
from .const import BINARY_SENSORS, DOMAIN
from .entity_discovery import setup_entity_discovery

_LOGGER = logging.getLogger(__name__)

_STRUCTURALLY_UNSUPPORTED_BACKDOOR_TYPES = {
    VehicleFeatures.Trunk: {"tailgate"},
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the binary_sensor platform."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]
    registry = er.async_get(hass)

    def discover_binary_sensors():
        for vehicle in coordinator.data or []:
            for entity_config in BINARY_SENSORS:
                if vehicle.electric is False and cast(
                    bool, entity_config["electric"]
                ):
                    continue
                if vehicle.subscribed is False and cast(
                    bool, entity_config["subscription"]
                ):
                    continue
                feature = cast(VehicleFeatures, entity_config["feature"])
                unsupported_backdoor_types = (
                    _STRUCTURALLY_UNSUPPORTED_BACKDOOR_TYPES.get(feature)
                )
                if (
                    unsupported_backdoor_types
                    and getattr(vehicle, "backdoor_type", None)
                    in unsupported_backdoor_types
                ):
                    stale_entity_id = registry.async_get_entity_id(
                        "binary_sensor",
                        DOMAIN,
                        vehicle_entity_unique_id(
                            vehicle.vin,
                            cast(str, entity_config["name"]),
                        ),
                    )
                    if stale_entity_id is not None:
                        _LOGGER.info(
                            "Removing %s because it does not apply to "
                            "backdoor type %s",
                            stale_entity_id,
                            vehicle.backdoor_type,
                        )
                        registry.async_remove(stale_entity_id)
                    continue
                if vehicle.features.get(feature) is None:
                    continue
                yield ToyotaBinarySensor(
                    feature,
                    cast(str, entity_config["icon"]),
                    cast(BinarySensorDeviceClass, entity_config["device_class"]),
                    coordinator,
                    entity_config["name"],
                    vehicle.vin,
                )

    setup_entity_discovery(
        config_entry,
        coordinator,
        async_add_devices,
        discover_binary_sensors,
    )


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

        if self.device_class == BinarySensorDeviceClass.LOCK:
            if isinstance(sensor, ToyotaLockableOpening):
                return None if sensor.locked is None else not sensor.locked
            return None
        if isinstance(sensor, ToyotaOpening):
            return None if sensor.closed is None else not sensor.closed
        if isinstance(sensor, ToyotaRemoteStart):
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
        sensor = self.feature(self._vehicle_feature)
        if sensor is None:
            return False
        if self.device_class == BinarySensorDeviceClass.LOCK:
            return (
                isinstance(sensor, ToyotaLockableOpening)
                and sensor.locked is not None
            )
        if (
            self.device_class == BinarySensorDeviceClass.DOOR
            and isinstance(sensor, ToyotaOpening)
        ):
            return sensor.closed is not None
        return True
