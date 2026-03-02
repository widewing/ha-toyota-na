import asyncio
from typing import Any

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart


from homeassistant.components.lock import (
    LockEntity,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import COMMAND_MAP, DOMAIN, DOOR_LOCK, DOOR_UNLOCK


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the binary_sensor platform."""
    locks = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        if vehicle.subscribed is False:
            continue
        locks.append(
            ToyotaLock(
                coordinator,
                "",
                vehicle.vin,
            )
        )

    async_add_devices(locks, True)


class ToyotaLock(ToyotaNABaseEntity, LockEntity):

    _state_changing = False

    def __init__(
        self,
        vin,
        *args: Any,
    ):
        super().__init__(vin, *args)

    @property
    def icon(self):
        return "mdi:car-key"

    @property
    def is_locked(self):
        if self.vehicle is None:
            return None

        all_locks = [
            feature
            for feature in self.vehicle.features.values()
            if isinstance(feature, ToyotaLockableOpening)
        ]

        if not all_locks:
            return None

        return all(lock.locked for lock in all_locks)

    @property
    def is_locking(self):
        return self._state_changing is True and self.is_locked is False

    @property
    def is_unlocking(self):
        return self._state_changing is True and self.is_locked is True

    async def async_lock(self, **kwargs):
        """Lock all or specified locks. A code to lock the lock with may optionally be specified."""
        await self.toggle_lock(DOOR_LOCK)

    async def async_unlock(self, **kwargs):
        """Unlock all or specified locks. A code to unlock the lock with may optionally be specified."""
        await self.toggle_lock(DOOR_UNLOCK)

    async def toggle_lock(self, command: str):
        """Set the lock state via the provided command string."""
        if self.vehicle is not None:
            self._state_changing = True
            self.async_write_ha_state()
            await self.vehicle.send_command(COMMAND_MAP[command])
            self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self):
        """Poll for updated vehicle state after a command, then refresh the coordinator."""
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
        return self.vehicle is not None
