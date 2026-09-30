from typing import Any, Union, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.unit_conversion import PressureConverter

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN, SENSORS
from .entity_discovery import setup_entity_discovery


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the sensor platform."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    def discover_sensors():
        for vehicle in coordinator.data or []:
            for entity_config in SENSORS:
                vehicle_feature = cast(
                    VehicleFeatures, entity_config["feature"]
                )
                feature = vehicle.features.get(vehicle_feature)
                if isinstance(feature, ToyotaNumeric):
                    if vehicle.electric is False and cast(
                        bool, entity_config["electric"]
                    ):
                        continue
                    if vehicle.subscribed is False and cast(
                        bool, entity_config["subscription"]
                    ):
                        continue
                    yield ToyotaNumericSensor(
                        vehicle_feature,
                        cast(str, entity_config["icon"]),
                        cast(str, entity_config["unit"]),
                        cast(SensorStateClass, entity_config["state_class"]),
                        coordinator,
                        entity_config["name"],
                        vehicle.vin,
                    )

    setup_entity_discovery(
        config_entry,
        coordinator,
        async_add_devices,
        discover_sensors,
    )


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
            if (
                self._unit_of_measurement == UnitOfPressure.PSI
                and feat.value is not None
                and feat.unit
                and feat.unit != UnitOfPressure.PSI
            ):
                return PressureConverter.convert(feat.value, feat.unit, UnitOfPressure.PSI)
            return feat.value

    @property
    def available(self):
        return isinstance(self.feature(self._vehicle_feature), ToyotaNumeric)


    @property
    def state_class(self):
        return self._state_class

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
