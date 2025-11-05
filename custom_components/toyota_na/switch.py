"""Toyota switch entities."""
import logging
from typing import Any

from toyota_na.vehicle.base_vehicle import RemoteRequestCommand, ToyotaVehicle, VehicleFeatures

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Toyota switches by config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for index, vehicle in enumerate(coordinator.data):
        # Only add remote start switch if vehicle has remote subscription
        if vehicle.subscribed:
            entities.append(ToyotaRemoteStartSwitch(coordinator, vehicle, index))
    async_add_entities(entities)


class ToyotaRemoteStartSwitch(ToyotaNABaseEntity, SwitchEntity):
    """Representation of a Toyota remote start switch."""

    def __init__(self, coordinator, vehicle: ToyotaVehicle, index: int):
        """Initialize the remote start switch."""
        super().__init__(coordinator, vehicle, index)
        self._attr_name = f"{vehicle.model_name} Remote Start"
        self._attr_unique_id = f"{vehicle.vin}_remote_start_switch"
        self._attr_icon = "mdi:car-key"

    @property
    def is_on(self) -> bool:
        """Return true if vehicle is remotely started."""
        if VehicleFeatures.RemoteStartStatus in self.vehicle.features:
            remote_status = self.vehicle.features[VehicleFeatures.RemoteStartStatus]
            return remote_status.on if hasattr(remote_status, 'on') else False
        return False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and VehicleFeatures.RemoteStartStatus in self.vehicle.features
            and self.vehicle.subscribed
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the remote start."""
        try:
            _LOGGER.info(f"Remote starting {self.vehicle.model_name} (VIN: {self.vehicle.vin})")
            await self.vehicle.send_command(RemoteRequestCommand.EngineStart)
            # Wait a moment for the command to process
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to remote start vehicle: {e}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the remote start."""
        try:
            _LOGGER.info(f"Remote stopping {self.vehicle.model_name} (VIN: {self.vehicle.vin})")
            await self.vehicle.send_command(RemoteRequestCommand.EngineStop)
            # Wait a moment for the command to process
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to remote stop vehicle: {e}")
            raise

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        if VehicleFeatures.RemoteStartStatus in self.vehicle.features:
            remote_status = self.vehicle.features[VehicleFeatures.RemoteStartStatus]
            if hasattr(remote_status, 'date'):
                attrs["last_started"] = remote_status.date
            if hasattr(remote_status, 'timer'):
                attrs["timer_remaining"] = remote_status.timer
        return attrs
