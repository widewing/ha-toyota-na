"""Diagnostics support for ha-toyota-na."""
from __future__ import annotations

import logging

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from toyota_na.client import ToyotaOneClient

from .const import DOMAIN
from .vehicle_helpers import endpoint_generation

_LOGGER = logging.getLogger(__name__)

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_PASSWORD,
    "ctsLinks",  # contains a vin number
    "device_id",
    "id_token",
    "imei",
    "refresh_token",
    "subscriptionID",  # contains a vin number
    "username",
    "vin",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    client: ToyotaOneClient = hass.data[DOMAIN][config_entry.entry_id][
        "toyota_na_client"
    ]

    # We don't directly expose this from the vehicle api abstraction, but it's critical to dump this in diagnostics for debugging
    user_vehicle_list = await client.get_user_vehicle_list()
    
    vehicle_status = []
    telemetry = []
    engine_status = []
    electric_status = []

    for vehicle in user_vehicle_list:
        user_vehicle_status = None
        user_telemetry = None
        user_engine_status = None
        user_electric_status = None
        vin = vehicle["vin"]
        api_generation = vehicle["generation"]
        generation = endpoint_generation(api_generation)
        region = vehicle.get("region") or "US"
        
        try:
            if api_generation == "24MM":
                user_vehicle_status = await client.graphql_get_vehicle_status(
                    vin,
                    vehicle.get("backdoorType"),
                    region,
                )
            elif generation == "17CY":
                user_vehicle_status = await client.get_vehicle_status_17cy(
                    vin, region
                )
            elif generation == "17CYPLUS":
                user_vehicle_status = await client.get_vehicle_status_17cyplus(
                    vin, region
                )
        except Exception as err:
            _LOGGER.debug(
                "Vehicle status diagnostics failed for VIN ...%s: %s",
                vin[-4:],
                err,
            )

        try:
            user_telemetry = await client.get_telemetry(
                vin, region, generation
            )
        except Exception as err:
            _LOGGER.debug(
                "Telemetry diagnostics failed for VIN ...%s: %s", vin[-4:], err
            )

        try:
            if generation == "17CY":
                user_engine_status = await client.get_engine_status_17cy(
                    vin, region
                )
            elif generation == "17CYPLUS" and api_generation != "24MM":
                user_engine_status = await client.get_engine_status_17cyplus(
                    vin, region
                )
        except Exception as err:
            _LOGGER.debug(
                "Engine status diagnostics failed for VIN ...%s: %s",
                vin[-4:],
                err,
            )
            
        try:
            if api_generation != "24MM":
                user_electric_status = await client.get_electric_status(
                    vin, region=region
                )
        except Exception as err:
            _LOGGER.debug(
                "Electric status diagnostics failed for VIN ...%s: %s",
                vin[-4:],
                err,
            )

        vehicle_status.append(user_vehicle_status)
        telemetry.append(user_telemetry)
        engine_status.append(user_engine_status)
        electric_status.append(user_electric_status)

    return async_redact_data(
        {
            "config_entry": async_redact_data(dict(config_entry.data), TO_REDACT),
            "vehicle_list": {"data": user_vehicle_list},
            "vehicle_status": {"data": vehicle_status},
            "telemetry": {"data": telemetry},
            "engine_status": {"data": engine_status},
            "electric_status": {"data": electric_status},
        },
        TO_REDACT,
    )
