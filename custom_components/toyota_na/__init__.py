import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import (
    device_registry as dr,
    service,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from toyota_na import ToyotaOneClient, ToyotaOneAuth
from toyota_na.exceptions import AuthError, LoginError

import voluptuous as vol

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "device_tracker"]

SERVICE_DOOR_LOCK = "door_lock"
SERVICE_DOOR_UNLOCK = "door_unlock"
SERVICE_ENGINE_START = "engine_start"
SERVICE_ENGINE_STOP = "engine_stop"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

    client = ToyotaOneClient(
        ToyotaOneAuth(
            initial_tokens=entry.data["tokens"],
            callback=lambda tokens: update_tokens(tokens, hass, entry)
        )
    )
    try:
        await client.auth.check_tokens()
    except AuthError as e:
        raise ConfigEntryAuthFailed(e) from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=lambda: update_vehicles_status(client, entry),
        update_interval=timedelta(minutes=1),
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
        remote_action = service_call.service.replace("_", "-")

        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:

                vin = identifier[1]

                _LOGGER.info(
                    "Handling service call %s for %s ",
                    remote_action,
                    vin,
                )

                await client.remote_request(vin, remote_action)

        return True

    hass.services.async_register(
        DOMAIN, SERVICE_DOOR_UNLOCK, async_service_handle)
    hass.services.async_register(
        DOMAIN, SERVICE_DOOR_LOCK, async_service_handle)
    hass.services.async_register(
        DOMAIN, SERVICE_ENGINE_START, async_service_handle)
    hass.services.async_register(
        DOMAIN, SERVICE_ENGINE_STOP, async_service_handle)

    return True


def update_tokens(tokens, hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("Tokens refreshed, updating ConfigEntry")
    data = dict(entry.data)
    data["tokens"] = tokens
    hass.config_entries.async_update_entry(entry, data=data)


async def update_vehicles_status(client: ToyotaOneClient, entry: ConfigEntry):
    try:
        _LOGGER.debug("Updating vehicle status")
        vehicles = await client.get_user_vehicle_list()
        vehicles = {v["vin"]: {"info": v} for v in vehicles}
        for vin, vehicle in vehicles.items():
            if vehicle["info"]["remoteSubscriptionStatus"] != 'ACTIVE':
                continue
            try:
                vehicle["status"] = await client.get_vehicle_status(vin)
            except Exception as e:
                _LOGGER.warn("Error fetching vehicle status")
            try:
                vehicle["health_status"] = await client.get_vehicle_health_status(vin)
            except Exception as e:
                _LOGGER.warn("Error fetching vehicle health status")
            try:
                vehicle["odometer_detail"] = await client.get_odometer_detail(vin)
            except Exception as e:
                _LOGGER.warn("Error fetching odometer detail")
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
