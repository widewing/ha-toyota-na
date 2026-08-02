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
        # Deliberately just the sensor name, not "{sensor_name} {vehicle model}" -- the manual
        # concatenation this used to do produced confusing/doubled-looking names in the UI
        # (e.g. a device page showing "2023 Highlander Front Driver Door 2023 Highlander").
        # Note this class does NOT set `_attr_has_entity_name = True`, so Home Assistant isn't
        # composing the device name in automatically either -- the friendly name really is just
        # the bare sensor name (e.g. "Front Driver Door"), distinguished from the same sensor on
        # another vehicle only by which device it's grouped under, not by the name itself.
        # Migrating to has_entity_name=True (HA's modern entity-naming convention) would be a
        # bigger, separate change -- it affects every existing entity_id.
        if self.vehicle is not None:
            return self.sensor_name

    @property
    def unique_id(self):
        # Plain vin+sensor_name, no config-entry namespacing. A vehicle visible to two Toyota
        # accounts (Toyota "family sharing") could in principle collide here if both accounts'
        # entries tried to create entities for the same VIN -- that's prevented by only ever
        # letting one config entry create entities for a given VIN in the first place (the VIN
        # claim guard in __init__.py, see async_claim_vehicles()). That external invariant is
        # what keeps this safe; it isn't enforced by anything in this file.
        return f"{self.vin}.{self.sensor_name}"

    @property
    def device_info(self) -> DeviceInfo:
        model = None

        if self.vehicle is not None:
            model = f"{self.vehicle.model_year} {self.vehicle.model_name}"

        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": model,
            "model": model,
            "manufacturer": "Toyota Motor North America",
        }

    @property
    def vehicle(self) -> Union[ToyotaVehicle, None]:
        """Return the vehicle."""
        return next((v for v in self.coordinator.data if v.vin == self.vin), None)
