from ctypes import cast
from datetime import timedelta, datetime
import logging
import asyncio

from toyota_na.auth import ToyotaOneAuth
from toyota_na.client import ToyotaOneClient

# Patch client code
from .patch_client import get_electric_status, api_request
ToyotaOneClient.get_electric_status = get_electric_status
ToyotaOneClient.api_request = api_request

# Patch base_vehicle
import toyota_na.vehicle.base_vehicle
from .patch_base_vehicle import ApiVehicleGeneration
toyota_na.vehicle.base_vehicle.ApiVehicleGeneration = ApiVehicleGeneration
from .patch_base_vehicle import VehicleFeatures
toyota_na.vehicle.base_vehicle.VehicleFeatures = VehicleFeatures
from .patch_base_vehicle import RemoteRequestCommand
toyota_na.vehicle.base_vehicle.RemoteRequestCommand = RemoteRequestCommand
from .patch_base_vehicle import ToyotaVehicle
toyota_na.vehicle.base_vehicle.ToyotaVehicle = ToyotaVehicle

# Patch seventeen_cy_plus
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle
from .patch_seventeen_cy_plus import SeventeenCYPlusToyotaVehicle
toyota_na.vehicle.vehicle_generations.seventeen_cy_plus.SeventeenCYPlusToyotaVehicle = SeventeenCYPlusToyotaVehicle

# Patch seventeen_cy
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from .patch_seventeen_cy import SeventeenCYToyotaVehicle
toyota_na.vehicle.vehicle_generations.seventeen_cy.SeventeenCYToyotaVehicle = SeventeenCYToyotaVehicle

from toyota_na.exceptions import AuthError, LoginError
from toyota_na.vehicle.base_vehicle import RemoteRequestCommand, ToyotaVehicle

#Patch get_vehicles
from .patch_vehicle import get_vehicles
#from toyota_na.vehicle.vehicle import get_vehicles

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COMMAND_MAP,
    DOMAIN,
    ENGINE_START,
    ENGINE_STOP,
    HAZARDS_ON,
    HAZARDS_OFF,
    DOOR_LOCK,
    DOOR_UNLOCK,
    REFRESH,
    UPDATE_INTERVAL,
    REFRESH_STATUS_INTERVAL
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "device_tracker", "lock", "sensor"]

async def async_setup(hass: HomeAssistant, _processed_config) -> bool:
    @service.verify_domain_control(hass, DOMAIN)
    async def async_service_handle(service_call: ServiceCall) -> None:
        """Handle dispatched services."""

        device_registry = dr.async_get(hass)
        device = device_registry.async_get(service_call.data["vehicle"])
        remote_action = service_call.service

        if device is None:
            _LOGGER.warning("Device does not exist")
            return

        # There is currently not a case with this integration where
        # the device will have more or less than one config entry
        if len(device.config_entries) != 1:
            _LOGGER.warning("Device missing config entry")
            return

        entry_id = list(device.config_entries)[0]

        if entry_id not in hass.data[DOMAIN]:
            _LOGGER.warning("Config entry not found")
            return

        if "coordinator" not in hass.data[DOMAIN][entry_id]:
            _LOGGER.warning("Coordinator not found")
            return

        coordinator = hass.data[DOMAIN][entry_id]["coordinator"]

        if coordinator.data is None:
            _LOGGER.warning("No coordinator data")
            return

        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:

                vin = identifier[1]
                for vehicle in coordinator.data:
                    if vehicle.vin == vin and remote_action.upper() == "REFRESH" and vehicle.subscribed:
                        await vehicle.poll_vehicle_refresh()
                        # TODO: This works great and prevents us from unnecessarily hitting Toyota. But we can and should
                        # probably do stuff like this in the library where we can better control which APIs we hit to refresh our in-memory data.
                        coordinator.async_set_updated_data(coordinator.data)
                        await asyncio.sleep(10)
                        await coordinator.async_request_refresh()
                    elif vehicle.vin == vin and vehicle.subscribed:
                        await vehicle.send_command(COMMAND_MAP[remote_action])
                        break

                _LOGGER.info("Handling service call %s for %s ", remote_action, vin)

        return

    hass.services.async_register(DOMAIN, ENGINE_START, async_service_handle)
    hass.services.async_register(DOMAIN, ENGINE_STOP, async_service_handle)
    hass.services.async_register(DOMAIN, HAZARDS_ON, async_service_handle)
    hass.services.async_register(DOMAIN, HAZARDS_OFF, async_service_handle)
    hass.services.async_register(DOMAIN, DOOR_LOCK, async_service_handle)
    hass.services.async_register(DOMAIN, DOOR_UNLOCK, async_service_handle)
    hass.services.async_register(DOMAIN, REFRESH, async_service_handle)

    return True

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
        _LOGGER.exception(e)
        raise ConfigEntryAuthFailed(e) from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=lambda: update_vehicles_status(hass, client, entry),
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "toyota_na_client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def update_tokens(tokens: dict[str, str], hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("Tokens refreshed, updating ConfigEntry")
    data = dict(entry.data)
    data["tokens"] = tokens
    hass.config_entries.async_update_entry(entry, data=data)


async def update_vehicles_status(hass: HomeAssistant, client: ToyotaOneClient, entry: ConfigEntry):
    need_refresh = False
    need_refresh_before = datetime.utcnow().timestamp() - REFRESH_STATUS_INTERVAL
    if "last_refreshed_at" not in entry.data or entry.data["last_refreshed_at"] < need_refresh_before:
        need_refresh = True
    try:
        _LOGGER.debug("Updating vehicle status")
        raw_vehicles = await get_vehicles(client)
        vehicles: list[ToyotaVehicle] = []
        for vehicle in raw_vehicles:
            if vehicle.subscribed is not True:
                _LOGGER.warning(
                    f"Your {vehicle.model_year} {vehicle.model_name} needs a remote services subscription to fully work with Home Assistant."
                )
            if need_refresh and vehicle.subscribed:
                await vehicle.poll_vehicle_refresh()
            vehicles.append(vehicle)
        entry_data = dict(entry.data)
        entry_data["last_refreshed_at"] = datetime.utcnow().timestamp()
        hass.config_entries.async_update_entry(entry, data=entry_data)
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
