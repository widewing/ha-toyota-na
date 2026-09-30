import asyncio
import logging
from typing import Any

from homeassistant.components.lock import (
    LockEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from toyota_na.vehicle.base_vehicle import ToyotaVehicle
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening

from .base_entity import ToyotaNABaseEntity
from .const import (
    COMMAND_MAP,
    COMMAND_REFRESH_DELAY,
    DOMAIN,
    DOOR_LOCK,
    DOOR_UNLOCK,
)
from .entity_discovery import setup_entity_discovery
from .wake_policy import record_vehicle_wake

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the binary_sensor platform."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    def discover_locks():
        for vehicle in coordinator.data or []:
            if vehicle.subscribed is False or not (
                vehicle.supports_command(COMMAND_MAP[DOOR_LOCK])
                and vehicle.supports_command(COMMAND_MAP[DOOR_UNLOCK])
            ):
                continue
            yield ToyotaLock(
                config_entry,
                coordinator,
                "",
                vehicle.vin,
            )

    setup_entity_discovery(
        config_entry,
        coordinator,
        async_add_devices,
        discover_locks,
    )


class ToyotaLock(ToyotaNABaseEntity, LockEntity):

    _state_changing = False

    @property
    def name(self):
        """Use the vehicle name for its primary lock entity."""
        return None

    def __init__(
        self,
        config_entry: ConfigEntry,
        *args: Any,
    ):
        super().__init__(*args)
        self._config_entry = config_entry
        self._state_changing = False

    @property
    def icon(self):
        return "mdi:car-key"

    @property
    def is_locked(self):
        if self.vehicle is None:
            return None

        lock_states = [
            feature.locked
            for feature in self.vehicle.features.values()
            if isinstance(feature, ToyotaLockableOpening)
            and feature.locked is not None
        ]

        if not lock_states:
            return None

        return all(lock_states)

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
            try:
                await self.vehicle.send_command(COMMAND_MAP[command])
            except Exception:
                self._state_changing = False
                self.async_write_ha_state()
                raise
            record_vehicle_wake(self.hass, self._config_entry, self.vin)
            self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self):
        """Refresh coordinator state after a remote command."""
        try:
            await asyncio.sleep(COMMAND_REFRESH_DELAY)
            await self.coordinator.async_request_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Post-command refresh failed: %s", err)
        finally:
            self._state_changing = False
            self.async_write_ha_state()

    @property
    def available(self):
        vehicle = self.vehicle
        return (
            vehicle is not None
            and vehicle.subscribed
            and vehicle.supports_command(COMMAND_MAP[DOOR_LOCK])
            and vehicle.supports_command(COMMAND_MAP[DOOR_UNLOCK])
        )
