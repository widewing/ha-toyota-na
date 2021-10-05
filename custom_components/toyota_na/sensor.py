from homeassistant.const import PERCENTAGE

from .const import DOMAIN
from .base_entity import ToyotaNABaseEntity


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the sensor platform."""
    sensors = []

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    sensor_types = [
        (ToyotaNAFuelSensor, "fuel level"),
        (ToyotaNAOilSensor, "oil status"),
        (ToyotaNAKeyBatSensor, "key battery status"),
        (lambda *args: ToyotaNAOdometerSensor("odometer", *args), "odometer"),
        (lambda *args: ToyotaNAOdometerSensor("tripA", *args), "trip a"),
        (lambda *args: ToyotaNAOdometerSensor("tripB", *args), "trip b"),
        (lambda *args: ToyotaNAOdometerSensor("distanceToEmpty", *args), "distance to empty"),
        (lambda *args: ToyotaNAOdometerSensor("nextService", *args), "next service"),
        (lambda *args: ToyotaNATirePressureSensor("flTirePressure", *args), "tire pressure front left"),
        (lambda *args: ToyotaNATirePressureSensor("frTirePressure", *args), "tire pressure front right"),
        (lambda *args: ToyotaNATirePressureSensor("rlTirePressure", *args), "tire pressure rear left"),
        (lambda *args: ToyotaNATirePressureSensor("rrTirePressure", *args), "tire pressure rear right")
    ]

    for vin in coordinator.data:
        for sensor_class, sensor_name in sensor_types:
            sensor = sensor_class(coordinator, vin, sensor_name)
            if sensor.available:
                sensors.append(sensor)

        door_window_sensor = ToyotaNADoorWindowSensor(None, None, coordinator, vin, None)
        for category, section in door_window_sensor.list_sections():
            sensors.append(
                ToyotaNADoorWindowSensor(category, section, coordinator, vin, f"{category} {section}")
            )

    async_add_devices(sensors, True)


class ToyotaNAOdometerSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:counter"

    def __init__(self, field_name, *args):
        super().__init__(*args)
        self.field_name = field_name

    @property
    def unit_of_measurement(self):
        return self.vehicle_odometer_detail[self.field_name]["unit"]

    @property
    def state(self):
        return int(self.vehicle_odometer_detail[self.field_name]["value"])

    @property
    def available(self):
        return self.field_name in self.vehicle_odometer_detail

class ToyotaNAFuelSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:gas-station"

    @property
    def unit_of_measurement(self):
        return PERCENTAGE

    @property
    def state(self):
        return int(self.vehicle_odometer_detail["fuelLevel"])

    @property
    def available(self):
        return "fuelLevel" in self.vehicle_odometer_detail

class ToyotaNAOilSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:oil-level"

    @property
    def state(self):
        return int(self.vehicle_health_status["quantityOfEngOilStatus"])

    @property
    def available(self):
        return "quantityOfEngOilStatus" in self.vehicle_health_status

class ToyotaNAKeyBatSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:key-wireless"

    @property
    def state(self):
        return int(self.vehicle_health_status["smartKeyBatStatus"])

    @property
    def available(self):
        return "smartKeyBatStatus" in self.vehicle_health_status


class ToyotaNATirePressureSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:car-tire-alert"

    def __init__(self, field_name, *args):
        super().__init__(*args)
        self.field_name = field_name

    @property
    def unit_of_measurement(self):
        return self.vehicle_odometer_detail[self.field_name]["unit"]

    @property
    def state(self):
        return int(self.vehicle_odometer_detail[self.field_name]["value"])

    @property
    def available(self):
        return self.field_name in self.vehicle_odometer_detail

class ToyotaNADoorWindowSensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:car-door"

    def __init__(self, category, section, *args):
        super().__init__(*args)
        self.category = category
        self.section = section

    def list_sections(self):
        return [
            (category["category"], section["section"])
            for category in self.vehicle_status["vehicleStatus"]
            for section in category["sections"]
        ]

    @property
    def state(self):
        for category in self.vehicle_status["vehicleStatus"]:
            if category["category"] == self.category:
                for section in category["sections"]:
                    if section["section"] == self.section:
                        return " ".join(v["value"] for v in section["values"])
        return None

    @property
    def available(self):
        return self.state is not None
