import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from toyota_na import ToyotaOneClient, ToyotaOneAuth

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "device_tracker"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})
    
    client = ToyotaOneClient(
        ToyotaOneAuth(
            initial_tokens=entry.data["tokens"],
            callback=lambda tokens: update_tokens(tokens, hass, entry)
        )
    )
    await client.auth.check_tokens()
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=lambda: update_vehicles_status(client),
        update_interval=timedelta(minutes=1),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "toyota_na_client": client,
        "coordinator": coordinator,
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


def update_tokens(tokens, hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.warn("Tokens refreshed, updating ConfigEntry")
    data = dict(entry.data)
    data["tokens"] = tokens
    hass.config_entries.async_update_entry(entry, data=data)


async def update_vehicles_status(client: ToyotaOneClient):
    try:
        _LOGGER.warn("Updating vehicle status")
        vehicles = await client.get_user_vehicle_list()
        vehicles = {v["vin"]: {"info": v} for v in vehicles}
        for vin, vehicle in vehicles.items():
            vehicle["status"] = await client.get_vehicle_status(vin)
            vehicle["health_status"] = await client.get_vehicle_health_status(vin)
            vehicle["odometer_detail"] = await client.get_odometer_detail(vin)
        return vehicles
    except Exception as e:
        _LOGGER.exception("Error fetching data")
        raise UpdateFailed() from e


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
