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

from .base_entity import ToyotaNABaseEntity
from .const import BINARY_SENSORS, DOMAIN

_LOGGER = logging.getLogger(__name__)


# Body styles that structurally cannot have a given feature, regardless of what any
# particular API poll happens to report. Used to actively clean up entities that were
# created once (e.g. under an older integration version) and then orphaned into permanent
# "unavailable" once the code correctly stopped populating them -- Home Assistant doesn't
# prune entities a platform silently stops providing, so without this they linger forever.
#
# Only Trunk/"tailgate" is listed because it's the only case actually confirmed via live
# testing (a pickup truck's tailgate reports as `backdoor_type: "tailgate"`, and the API never
# sends a Trunk feature value for it). Other body-style mismatches may well exist (e.g. no
# moonroof, no rear doors on a 2-door) but haven't been observed/confirmed -- add an entry here
# the same way, keyed by whatever `backdoor_type` (or other vehicle attribute) value structurally
# rules the feature out, once one is confirmed.
_STRUCTURALLY_UNSUPPORTED_BACKDOOR_TYPES = {
    VehicleFeatures.Trunk: {"tailgate"},
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the binary_sensor platform."""
    binary_sensors = []
    registry = er.async_get(hass)

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

                unsupported_backdoor_types = _STRUCTURALLY_UNSUPPORTED_BACKDOOR_TYPES.get(
                    feature_sensor["feature"]
                )
                if unsupported_backdoor_types and vehicle.backdoor_type in unsupported_backdoor_types:
                    # Rebuilds ToyotaNABaseEntity.unique_id's format (base_entity.py) by hand,
                    # since there's no entity object here yet to ask -- if that format ever
                    # changes, this must change with it or stale-entity cleanup silently stops
                    # matching anything.
                    stale_entity_id = registry.async_get_entity_id(
                        "binary_sensor",
                        DOMAIN,
                        f"{vehicle.vin}.{entity_config['name']}",
                    )
                    if stale_entity_id:
                        _LOGGER.info(
                            "Removing %s: not applicable to this vehicle's body style (backdoorType=%s)",
                            stale_entity_id,
                            vehicle.backdoor_type,
                        )
                        registry.async_remove(stale_entity_id)
                    continue

                feature = vehicle.features.get(cast(VehicleFeatures, feature_sensor["feature"]))
                if feature is None:
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
        sensor = self.feature(self._vehicle_feature)
        if sensor is None:
            return False
        # Some API responses report lock state without reporting open/closed position
        # (closed is None in that case). The DOOR-class reading has nothing to show then --
        # surfacing it as unavailable is more honest than fabricating an "open" state.
        if (
            self.device_class == BinarySensorDeviceClass.DOOR
            and isinstance(sensor, ToyotaOpening)
            and sensor.closed is None
        ):
            return False
        return True
