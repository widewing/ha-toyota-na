"""Momentary Toyota remote-command buttons."""

from typing import Any

from toyota_na.vehicle.base_vehicle import ToyotaVehicle

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import BUZZER_WARNING, COMMAND_MAP, DOMAIN, SOUND_HORN


def _generation_value(vehicle: ToyotaVehicle) -> str:
    generation = getattr(vehicle, "generation", "")
    return str(getattr(generation, "value", generation))


def _supports_current_remote_commands(vehicle: ToyotaVehicle) -> bool:
    return _generation_value(vehicle) in {"17CYPLUS", "21MM", "24MM"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up momentary Toyota command buttons."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities: list[ButtonEntity] = []
    for vehicle in coordinator.data:
        if not vehicle.subscribed or not _supports_current_remote_commands(vehicle):
            continue
        entities.extend(
            (
                ToyotaCommandButton(
                    SOUND_HORN,
                    "mdi:bullhorn",
                    coordinator,
                    "Sound Horn",
                    vehicle.vin,
                ),
                ToyotaCommandButton(
                    BUZZER_WARNING,
                    "mdi:bell-alert",
                    coordinator,
                    "Buzzer Warning",
                    vehicle.vin,
                ),
            )
        )

    async_add_entities(entities, True)


class ToyotaCommandButton(ToyotaNABaseEntity, ButtonEntity):
    """Send a stateless Toyota remote command."""

    _attr_device_class = ButtonDeviceClass.IDENTIFY

    def __init__(self, command: str, icon: str, *args: Any) -> None:
        super().__init__(*args)
        self._command = command
        self._attr_icon = icon

    async def async_press(self) -> None:
        """Send the configured remote command."""
        vehicle = self.vehicle
        if vehicle is not None:
            await vehicle.send_command(COMMAND_MAP[self._command])

    @property
    def available(self) -> bool:
        vehicle = self.vehicle
        return (
            vehicle is not None
            and vehicle.subscribed
            and _supports_current_remote_commands(vehicle)
        )
