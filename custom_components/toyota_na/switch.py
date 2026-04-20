import asyncio
from typing import Any, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import COMMAND_MAP, DOMAIN, ENGINE_START, ENGINE_STOP


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the switch platform."""
    switches = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        if vehicle.subscribed is False:
            continue
        switches.append(ToyotaRemoteStartSwitch(coordinator, "Remote Start", vehicle.vin))

    async_add_devices(switches, True)


class ToyotaRemoteStartSwitch(ToyotaNABaseEntity, SwitchEntity):
    _attr_icon = "mdi:engine"
    _state_changing = False

    @property
    def unique_id(self):
        return f"{self.vin}.Remote Start.switch"

    @property
    def is_on(self):
        remote_start = cast(ToyotaRemoteStart, self.feature(VehicleFeatures.RemoteStartStatus))
        if remote_start is None:
            return False
        return bool(remote_start.on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_remote_command(ENGINE_START)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_remote_command(ENGINE_STOP)

    async def _send_remote_command(self, command: str) -> None:
        if self.vehicle is None:
            return

        self._state_changing = True
        self.async_write_ha_state()
        await self.vehicle.send_command(COMMAND_MAP[command])
        self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        try:
            await self.vehicle.poll_vehicle_refresh()
            await asyncio.sleep(10)
            self._state_changing = False
            await self.coordinator.async_request_refresh()
        except Exception:
            self._state_changing = False
            self.async_write_ha_state()

    @property
    def available(self):
        return self.vehicle is not None and self.vehicle.subscribed is True
