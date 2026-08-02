"""Cover entities for Toyota windows."""

import asyncio
from typing import Any

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import COMMAND_MAP, DOMAIN, WINDOWS_CLOSE, WINDOWS_OPEN


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
    """Set up Toyota power-window controls."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities = [
        ToyotaWindowsCover(coordinator, "Windows", vehicle.vin)
        for vehicle in coordinator.data
        if vehicle.subscribed and _supports_current_remote_commands(vehicle)
    ]
    async_add_entities(entities, True)


class ToyotaWindowsCover(ToyotaNABaseEntity, CoverEntity):
    """Open or close all remotely controllable vehicle windows."""

    _attr_device_class = CoverDeviceClass.WINDOW
    _attr_icon = "mdi:car-door"
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    _window_features = (
        VehicleFeatures.FrontDriverWindow,
        VehicleFeatures.FrontPassengerWindow,
        VehicleFeatures.RearDriverWindow,
        VehicleFeatures.RearPassengerWindow,
    )

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._optimistic_closed: bool | None = None

    @property
    def is_closed(self) -> bool | None:
        """Return whether all four windows are closed."""
        if self._optimistic_closed is not None:
            return self._optimistic_closed

        known_closed = 0
        for feature in self._window_features:
            window = self.feature(feature)
            closed = getattr(window, "closed", None)
            if closed is False:
                return False
            if closed is True:
                known_closed += 1
        if known_closed == len(self._window_features):
            return True
        return None

    @property
    def assumed_state(self) -> bool:
        """Flag incomplete Toyota window state as assumed."""
        return self.is_closed is None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open all power windows."""
        await self._send_command(WINDOWS_OPEN, False)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close all power windows."""
        await self._send_command(WINDOWS_CLOSE, True)

    async def _send_command(self, command: str, target_closed: bool) -> None:
        vehicle = self.vehicle
        if vehicle is None:
            return

        self._optimistic_closed = target_closed
        self.async_write_ha_state()
        try:
            await vehicle.send_command(COMMAND_MAP[command])
        except Exception:
            self._optimistic_closed = None
            self.async_write_ha_state()
            raise

        self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        """Refresh window positions after a completed command."""
        try:
            vehicle = self.vehicle
            if vehicle is not None:
                await vehicle.poll_vehicle_refresh()
            await asyncio.sleep(10)
            await self.coordinator.async_request_refresh()
        finally:
            self._optimistic_closed = None
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        vehicle = self.vehicle
        return (
            vehicle is not None
            and vehicle.subscribed
            and _supports_current_remote_commands(vehicle)
        )
