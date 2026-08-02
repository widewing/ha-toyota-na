import asyncio
from typing import Any, cast

from toyota_na.vehicle.base_vehicle import RemoteRequestCommand, ToyotaVehicle

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import COMMAND_BUTTONS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the button platform."""
    buttons = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        if vehicle.subscribed is False:
            continue

        for button_config in COMMAND_BUTTONS:
            command = cast(RemoteRequestCommand, button_config["command"])
            # Vehicles that don't support a command (per Toyota's remoteServiceCapabilities,
            # e.g. hazards on a truck without that capability) never get the button entity
            # created at all, rather than creating it and marking it unavailable/disabled. This
            # keeps a vehicle's dashboard free of buttons that can never work for it, at the
            # cost of the button not reappearing on its own if Toyota later reports the
            # capability as supported -- that would need a reload to pick up.
            if not vehicle.supports_command(command):
                continue
            buttons.append(
                ToyotaCommandButton(
                    command,
                    cast(str, button_config["icon"]),
                    coordinator,
                    button_config["name"],
                    vehicle.vin,
                )
            )

        buttons.append(
            ToyotaRefreshButton(
                coordinator,
                "Refresh",
                vehicle.vin,
            )
        )

    async_add_devices(buttons, True)


class ToyotaCommandButton(ToyotaNABaseEntity, ButtonEntity):
    _icon: str
    _command: RemoteRequestCommand

    def __init__(
        self,
        command: RemoteRequestCommand,
        icon: str,
        *args: Any,
    ):
        super().__init__(*args)
        self._command = command
        self._icon = icon

    @property
    def icon(self):
        return self._icon

    @property
    def available(self):
        return self.vehicle is not None

    async def async_press(self) -> None:
        """Send the remote command, then refresh the coordinator once the vehicle updates."""
        if self.vehicle is None:
            return
        await self.vehicle.send_command(self._command)
        self.hass.async_create_task(self._background_refresh())

    async def _background_refresh(self):
        """Poll for updated vehicle state after a command, then refresh the coordinator.

        The 10-second sleep gives Toyota's backend time to actually process the command and the
        vehicle time to report its new state before we ask for it -- polling immediately tends
        to just re-fetch the pre-command state. Runs as a fire-and-forget background task (see
        async_press()) so the button press itself returns immediately rather than blocking on
        this; failures here are swallowed rather than raised because there's nothing meaningful
        to surface for a background poll -- the command itself already succeeded or failed on
        its own, and the next scheduled coordinator refresh will pick up the real state
        regardless. Mirrors the same pattern used for the REFRESH service in __init__.py's
        async_service_handle -- see the TODO there for the same reasoning, and consider fixing
        both places together if this ever moves into the library.
        """
        try:
            await self.vehicle.poll_vehicle_refresh()
            await asyncio.sleep(10)
            await self.coordinator.async_request_refresh()
        except Exception:
            pass


class ToyotaRefreshButton(ToyotaNABaseEntity, ButtonEntity):
    @property
    def icon(self):
        return "mdi:refresh"

    @property
    def available(self):
        return self.vehicle is not None

    async def async_press(self) -> None:
        """Force Toyota to push a fresh status, then refresh the coordinator.

        The async_set_updated_data() call re-pushes the coordinator's *existing* data -- it
        looks like a no-op, but its purpose is to make every entity re-evaluate right away (e.g.
        pick up this button's own state/attributes changing) rather than wait for the real
        refresh below, which is deliberately delayed. See _background_refresh() on
        ToyotaCommandButton above for why the delay exists.
        """
        if self.vehicle is None:
            return
        await self.vehicle.poll_vehicle_refresh()
        self.coordinator.async_set_updated_data(self.coordinator.data)
        await asyncio.sleep(10)
        await self.coordinator.async_request_refresh()
