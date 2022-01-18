from homeassistant.const import PERCENTAGE
from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_DOOR,
    DEVICE_CLASS_LOCK,
    DEVICE_CLASS_WINDOW,
)

from .const import DOMAIN
from .base_entity import ToyotaNABaseEntity


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the sensor platform."""
    sensors = []

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    for vin in coordinator.data:
        door_window_sensor = ToyotaNADoorWindowBinarySensor(
            None, None, None, coordinator, vin, None)
        for category, section in door_window_sensor.list_sections():
            sensors.append(
                ToyotaNADoorWindowBinarySensor(category, section, coordinator, vin, f"{category} {section}")
            )

    async_add_devices(sensors, True)


class ToyotaNADoorWindowBinarySensor(ToyotaNABaseEntity):
    _attr_icon = "mdi:car-door"

    def __init__(self, category, section, device_class, *args):
        super().__init__(*args)
        self.category = category
        self.section = section
        self._attr_device_class = device_class

    def _class_from_section_value(self, section, value):
        s = section.lower()
        v = value.lower()
        if "window" in s:
            return DEVICE_CLASS_WINDOW
        if "lock" in v:
            return DEVICE_CLASS_LOCK
        return DEVICE_CLASS_DOOR

    def list_sections(self):
        return [
            (
                category["category"],
                section["section"],
                self._class_from_section_value(section["section"], state["value"]),
            )
            for category in self.vehicle_status["vehicleStatus"]
            for section in category["sections"]
            for state in section["values"]
        ]

    @property
    def state(self):
        for category in self.vehicle_status["vehicleStatus"]:
            if category["category"] == self.category:
                for section in category["sections"]:
                    if section["section"] == self.section:
                        vals = (v["value"].lower() for v in section["values"])
                        if self.device_class.lower() in ('door', 'window', ):
                            return 'opened' in vals
                        if self.device_class.lower() == 'lock':
                            return 'unlocked' in vals

        return None

    @property
    def available(self):
        return self.state is not None
