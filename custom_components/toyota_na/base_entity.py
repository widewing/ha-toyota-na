from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class ToyotaNABaseEntity(CoordinatorEntity):
    def __init__(self, coordinator, vin, sensor_name) -> None:
        super().__init__(coordinator)
        self.vin = vin
        self.sensor_name = sensor_name

    @property
    def name(self):
        return f"{self.sensor_name.title()} {self.device_info['name']}"

    @property
    def unique_id(self):
        return f"{self.vin}.{self.sensor_name}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": self.vin,
            "model": f'{self.vehicle_info["modelYear"]} {self.vehicle_info["modelDescription"]}',
            "manufacturer": "Toyota Motor North America",
        }
    
    @property
    def vehicle(self):
        return self.coordinator.data[self.vin]

    @property
    def vehicle_status(self):
        return self.vehicle["status"]

    @property
    def vehicle_info(self):
        return self.vehicle["info"]

    @property
    def vehicle_health_status(self):
        return self.vehicle["health_status"]

    @property
    def vehicle_odometer_detail(self):
        return self.vehicle["odometer_detail"]

    @property
    def available(self):
        return True
