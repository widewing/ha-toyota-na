from ctypes import cast
from datetime import timedelta
import logging

from toyota_na.auth import ToyotaOneAuth
from toyota_na.client import ToyotaOneClient
from toyota_na.exceptions import AuthError, LoginError
from toyota_na.vehicle.base_vehicle import RemoteRequestCommand, ToyotaVehicle
from toyota_na.vehicle.vehicle import get_vehicles

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "device_tracker", "sensor"]

SERVICE_DOOR_LOCK = "door_lock"
SERVICE_DOOR_UNLOCK = "door_unlock"
SERVICE_ENGINE_START = "engine_start"
SERVICE_ENGINE_STOP = "engine_stop"

commands = {
    SERVICE_DOOR_LOCK: RemoteRequestCommand.DoorLock,
    SERVICE_DOOR_UNLOCK: RemoteRequestCommand.DoorUnlock,
    SERVICE_ENGINE_START: RemoteRequestCommand.EngineStart,
    SERVICE_ENGINE_STOP: RemoteRequestCommand.EngineStop,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

    client = ToyotaOneClient(
        ToyotaOneAuth(
            initial_tokens=entry.data["tokens"],
            callback=lambda tokens: update_tokens(tokens, hass, entry),
        )
    )
    try:
        client.auth.set_tokens(entry.data["tokens"])
        await client.auth.check_tokens()
    except AuthError as e:
        raise ConfigEntryAuthFailed(e) from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=lambda: update_vehicles_status(client, entry),
        update_interval=timedelta(seconds=20),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "toyota_na_client": client,
        "coordinator": coordinator,
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    @service.verify_domain_control(hass, DOMAIN)
    async def async_service_handle(service_call: ServiceCall) -> None:
        """Handle dispatched services."""

        device_registry = dr.async_get(hass)
        device = device_registry.async_get(service_call.data["vehicle"])
        remote_action = service_call.service

        if device is None:
            _LOGGER.warning("Device does not exist")
            return

        if coordinator.data is None:
            _LOGGER.warning("No coordinator data")
            return

        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:

                vin = identifier[1]
                for vehicle in coordinator.data:
                    if vehicle.vin == vin:
                        await vehicle.send_command(commands[remote_action])
                        break

                _LOGGER.info("Handling service call %s for %s ", remote_action, vin)

        return

    hass.services.async_register(DOMAIN, SERVICE_DOOR_LOCK, async_service_handle)
    hass.services.async_register(DOMAIN, SERVICE_DOOR_UNLOCK, async_service_handle)
    hass.services.async_register(DOMAIN, SERVICE_ENGINE_START, async_service_handle)
    hass.services.async_register(DOMAIN, SERVICE_ENGINE_STOP, async_service_handle)

    return True


def update_tokens(tokens: dict[str, str], hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("Tokens refreshed, updating ConfigEntry")
    data = dict(entry.data)
    data["tokens"] = tokens
    hass.config_entries.async_update_entry(entry, data=data)


async def update_vehicles_status(client: ToyotaOneClient, entry: ConfigEntry):
    try:
        _LOGGER.debug("Updating vehicle status")
        raw_vehicles = await get_vehicles(client)
        vehicles: list[ToyotaVehicle] = []
        for vehicle in raw_vehicles:
            # if vehicle["info"]["remoteSubscriptionStatus"] != "ACTIVE":
            #     continue
            vehicles.append(vehicle)
        return vehicles
    except AuthError as e:
        try:
            client.auth.login(entry.data["username"], entry.data["password"])
        except LoginError:
            _LOGGER.exception("Error logging in")
            raise ConfigEntryAuthFailed(e) from e
    except Exception as e:
        _LOGGER.exception("Error fetching data")
        raise UpdateFailed(e) from e


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
