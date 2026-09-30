from typing import Union

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN


def vehicle_entity_unique_id(vin: str, sensor_name: str) -> str:
    """Return the stable unique ID shared by every vehicle entity."""
    return f"{vin}.{sensor_name}"


class ToyotaNABaseEntity(CoordinatorEntity[list[ToyotaVehicle]]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[list[ToyotaVehicle]],
        sensor_name: str,
        vin: str,
    ) -> None:
        super().__init__(coordinator)
        self.sensor_name = sensor_name
        self.vin = vin

    def feature(self, feature: VehicleFeatures):
        """Return the feature dict."""
        if self.vehicle is None:
            return
        return self.vehicle.features.get(feature)

    @property
    def name(self):
        return self.sensor_name

    @property
    def unique_id(self):
        return vehicle_entity_unique_id(self.vin, self.sensor_name)

    @property
    def device_info(self) -> DeviceInfo:
        model = None

        if self.vehicle is not None:
            model = f"{self.vehicle.model_year} {self.vehicle.model_name}"

        brand = self.vehicle.brand if self.vehicle is not None else "T"
        manufacturer = {
            "L": "Lexus",
        }.get(brand, "Toyota Motor North America")

        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": model,
            "model": model,
            "manufacturer": manufacturer,
        }

    @property
    def vehicle(self) -> Union[ToyotaVehicle, None]:
        """Return the vehicle."""
        return next((v for v in self.coordinator.data if v.vin == self.vin), None)
