from typing import Any, Union, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN, SENSORS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the sensor platform."""
    sensors = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        for feature_sensor in SENSORS:
            feature = vehicle.features.get(
                cast(VehicleFeatures, feature_sensor["feature"])
            )

            entity_config = feature_sensor
            if entity_config and isinstance(feature, ToyotaNumeric):
                if vehicle.electric is False and cast(bool, entity_config["electric"]):
                    continue
                if vehicle.subscribed is False and cast(bool, entity_config["subscription"]):
                    continue
                sensors.append(
                    ToyotaNumericSensor(
                        cast(VehicleFeatures, feature_sensor["feature"]),
                        cast(str, entity_config["icon"]),
                        cast(str, entity_config["unit"]),
                        cast(SensorStateClass, entity_config["state_class"]),
                        coordinator,
                        entity_config["name"],
                        vehicle.vin,
                    )
                )

    async_add_devices(sensors, True)


class ToyotaNumericSensor(ToyotaNABaseEntity):
    _icon: str
    _vehicle_feature: VehicleFeatures

    def __init__(
        self,
        vehicle_feature: VehicleFeatures,
        icon: str,
        unit_of_measurement: str,
        state_class: Union[SensorStateClass, str],
        *args: Any,
    ):
        super().__init__(*args)
        self._icon = icon
        self._state_class = state_class
        self._unit_of_measurement = unit_of_measurement
        self._vehicle_feature = vehicle_feature

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def state(self):
        feat = cast(ToyotaNumeric, self.feature(self._vehicle_feature))
        if feat:
            return feat.value

    @property
    def state_class(self):
        return self.feature(self._vehicle_feature) is not None

    @property
    def unit_of_measurement(self):

        # We need to poll the unit of measure from the service itself to ensure we're passing
        # the correct unit of measure to the sensor.
        if self._unit_of_measurement == "MI_OR_KM":
            feature = cast(ToyotaNumeric, self.feature(self._vehicle_feature))
            if hasattr(feature,'unit'):
                _unit = feature.unit
                if _unit == "mi":
                    return UnitOfLength.MILES
                elif _unit == "km":
                    return UnitOfLength.KILOMETERS

        return self._unit_of_measurement
