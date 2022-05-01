"""Diagnostics support for AccuWeather."""
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

    vehicle_details = []

    for vehicle in user_vehicle_list:
        try:
            user_vehicle_status = await client.get_vehicle_status(
                vin=vehicle["vin"], generation=vehicle["generation"]
            )

            user_vehicle_details = await client.get_vehicle_detail(
                vin=user_vehicle_list[0]["vin"]
            )

            vehicle_details.append(user_vehicle_status)
        except Exception:
            continue

    return async_redact_data(
        {
            "config_entry": async_redact_data(dict(config_entry.data), TO_REDACT),
            "api": {"vehicle_list": user_vehicle_list},
        },
        TO_REDACT,
    )
