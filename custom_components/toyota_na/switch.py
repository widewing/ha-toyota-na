"""Switch entities for controllable Toyota features."""

import asyncio
from typing import Any, cast

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import (
    CHARGE_START,
    CHARGE_STOP,
    COMMAND_MAP,
    DOMAIN,
    ENGINE_START,
    ENGINE_STOP,
    HAZARDS_OFF,
    HAZARDS_ON,
)


def _generation_value(vehicle: ToyotaVehicle) -> str:
    """Return the wire generation value for a vehicle."""
    generation = getattr(vehicle, "generation", "")
    return str(getattr(generation, "value", generation))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up controllable Toyota switches."""
    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    switches: list[SwitchEntity] = []
    for vehicle in coordinator.data:
        if not vehicle.subscribed:
            continue

        switches.extend(
            (
                ToyotaRemoteStartSwitch(coordinator, "Remote Start", vehicle.vin),
                ToyotaHazardsSwitch(coordinator, "Hazard Lights", vehicle.vin),
            )
        )
        if _generation_value(vehicle) == "24MM" and vehicle.electric:
            switches.append(
                ToyotaChargingSwitch(coordinator, "Vehicle Charging", vehicle.vin)
            )

    async_add_entities(switches, True)


class ToyotaCommandSwitch(ToyotaNABaseEntity, SwitchEntity):
    """Base class for a paired Toyota on/off command."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _clear_optimistic_after_refresh = True

    def __init__(
        self,
        on_command: str,
        off_command: str,
        icon: str,
        *args: Any,
    ) -> None:
        super().__init__(*args)
        self._on_command = on_command
        self._off_command = off_command
        self._attr_icon = icon
        self._optimistic_state: bool | None = None

    def _reported_state(self) -> bool | None:
        """Return the state reported by Toyota, if the service provides one."""
        return None

    @property
    def is_on(self) -> bool | None:
        """Return the reported or optimistic command state."""
        if self._optimistic_state is not None:
            return self._optimistic_state
        return self._reported_state()

    @property
    def assumed_state(self) -> bool:
        """Flag switches for which Toyota does not report a state."""
        return self._reported_state() is None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the on command."""
        await self._send_remote_command(self._on_command, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the off command."""
        await self._send_remote_command(self._off_command, False)

    async def _send_remote_command(self, command: str, target_state: bool) -> None:
        vehicle = self.vehicle
        if vehicle is None:
            return

        self._optimistic_state = target_state
        self.async_write_ha_state()
        try:
            await vehicle.send_command(COMMAND_MAP[command])
        except Exception:
            self._optimistic_state = None
            self.async_write_ha_state()
            raise

        self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        """Refresh Toyota state after a completed remote command."""
        try:
            vehicle = self.vehicle
            if vehicle is not None:
                await vehicle.poll_vehicle_refresh()
            await asyncio.sleep(10)
            await self.coordinator.async_request_refresh()
        finally:
            if self._clear_optimistic_after_refresh:
                self._optimistic_state = None
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return whether the vehicle can accept remote commands."""
        vehicle = self.vehicle
        return vehicle is not None and vehicle.subscribed


class ToyotaRemoteStartSwitch(ToyotaCommandSwitch):
    """Start or stop Toyota remote climate/engine operation."""

    def __init__(self, *args: Any) -> None:
        super().__init__(ENGINE_START, ENGINE_STOP, "mdi:car-clock", *args)

    def _reported_state(self) -> bool | None:
        remote_start = self.feature(VehicleFeatures.RemoteStartStatus)
        if isinstance(remote_start, ToyotaRemoteStart):
            return remote_start.on
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the runtime details returned by Toyota."""
        remote_start = cast(
            ToyotaRemoteStart | None,
            self.feature(VehicleFeatures.RemoteStartStatus),
        )
        if remote_start is None:
            return None

        attributes = {
            "end_time": remote_start.end_time,
            "minutes_remaining": remote_start.time_left,
            "start_time": remote_start.start_time,
            "total_runtime": remote_start.timer,
        }
        return {key: value for key, value in attributes.items() if value is not None}


class ToyotaHazardsSwitch(ToyotaCommandSwitch):
    """Turn the vehicle hazard lights on or off."""

    # Toyota accepts both commands but does not include hazard state in the
    # status response, so retain the most recently requested state.
    _clear_optimistic_after_refresh = False

    def __init__(self, *args: Any) -> None:
        super().__init__(HAZARDS_ON, HAZARDS_OFF, "mdi:hazard-lights", *args)


class ToyotaChargingSwitch(ToyotaCommandSwitch):
    """Start or stop immediate charging on a 24MM EV or PHEV."""

    def __init__(self, *args: Any) -> None:
        super().__init__(CHARGE_START, CHARGE_STOP, "mdi:ev-station", *args)

    def _reported_state(self) -> bool | None:
        charging = self.feature(VehicleFeatures.ChargingStatus)
        if isinstance(charging, ToyotaOpening):
            return not charging.closed
        return None

    @property
    def available(self) -> bool:
        vehicle = self.vehicle
        return (
            vehicle is not None
            and vehicle.subscribed
            and vehicle.electric
            and _generation_value(vehicle) == "24MM"
        )
