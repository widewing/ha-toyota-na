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
        if self.vehicle is not None:
            return f"{self.sensor_name} {self.device_info['name']}"

    @property
    def unique_id(self):
        return f"{self.vin}.{self.sensor_name}"

    @property
    def device_info(self) -> DeviceInfo:
        model = None
        device_info_dict = {
            "identifiers": {(DOMAIN, self.vin)},
            "manufacturer": "Toyota Motor North America",
        }

        if self.vehicle is not None:
            model = f"{self.vehicle.model_year} {self.vehicle.model_name}"
            device_info_dict["name"] = model
            device_info_dict["model"] = model

            # Add metadata if available
            if hasattr(self.vehicle, 'metadata') and self.vehicle.metadata:
                if self.vehicle.metadata.get('color'):
                    device_info_dict["configuration_url"] = "https://drivers.lexus.com/"
                    # Store metadata as sw_version for display
                    metadata_items = []
                    if self.vehicle.metadata.get('color'):
                        metadata_items.append(f"Color: {self.vehicle.metadata['color']}")
                    if self.vehicle.metadata.get('manufactured_date'):
                        metadata_items.append(f"Manufactured: {self.vehicle.metadata['manufactured_date']}")
                    if metadata_items:
                        device_info_dict["sw_version"] = " | ".join(metadata_items)

        return device_info_dict

    @property
    def vehicle(self) -> Union[ToyotaVehicle, None]:
        """Return the vehicle."""
        return next((v for v in self.coordinator.data if v.vin == self.vin), None)
