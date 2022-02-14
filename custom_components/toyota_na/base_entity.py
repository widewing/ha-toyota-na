from typing import Union

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN


class ToyotaNABaseEntity(CoordinatorEntity[list[ToyotaVehicle]]):
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
        return f"{self.sensor_name} {self.vin}"
        # return f"{self.sensor_name.title()} {self.device_info['name']}"

    @property
    def unique_id(self):
        return f"{self.vin}.{self.sensor_name}"

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": self.vin,
            # "model": f'{self.vehicle_info["modelYear"]} {self.vehicle_info["modelDescription"]}',
            "manufacturer": "Toyota Motor North America",
        }

    @property
    def vehicle(self) -> Union[ToyotaVehicle, None]:
        """Return the vehicle."""
        return next((v for v in self.coordinator.data if v.vin == self.vin), None)

    @property
    def available(self):
        return self.vehicle is not None
