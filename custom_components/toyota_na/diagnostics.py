"""Diagnostics support for ha-toyota-na."""
from __future__ import annotations

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

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_PASSWORD,
    "ctsLinks",  # contains a vin number
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

    user_vehicle_status = ""
    user_telemetry = ""
    user_engine_status = ""
    user_electric_status = ""

    for (i, vehicle) in enumerate(user_vehicle_list):
        vin=vehicle["vin"]

        if (vehicle["generation"] == "17CYPLUS" or vehicle["generation"] == "21MM"):
            generation = "17CYPLUS"
        elif vehicle["generation"] == "17CY":
            generation = "17CY"
        
        try:
            user_vehicle_status = await client.get_vehicle_status(vin, generation)
        except Exception:
            pass

        try:
            user_telemetry = await client.get_telemetry(vin, generation)
        except Exception:
            pass

        try:
            user_engine_status = await client.get_engine_status(vin, generation)
        except Exception:
            pass
            
        try:
            user_electric_status = await client.get_electric_status(vin)
        except Exception:
            pass

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
