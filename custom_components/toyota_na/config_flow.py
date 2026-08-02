import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from toyota_na import ToyotaOneAuth, ToyotaOneClient
from toyota_na.exceptions import AuthError

# Patch auth code
from .patch_auth import authorize, login
ToyotaOneAuth.authorize = authorize
ToyotaOneAuth.login = login
import json

from .const import CONF_MANAGED_VINS, DOMAIN, OPT_EXCLUDED_VINS
from .patch_base_vehicle import ApiVehicleGeneration

_LOGGER = logging.getLogger(__name__)


class ToyotaNAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Toyota (North America) connected services"""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ToyotaNAOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.client = ToyotaOneClient()
                self.user_info = user_input
                await self.client.auth.authorize(user_input["username"], user_input["password"])
                return await self.async_step_otp()
            except AuthError:
                errors["base"] = "not_logged_in"
                _LOGGER.error("Not logged in with username and password")
            except Exception as e:
                errors["base"] = "unknown"
                _LOGGER.exception("Unknown error with username and password")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
            errors=errors,
        )

    async def async_step_otp(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.otp_info = user_input
                data = await self.async_get_entry_data(self.client, errors)
                if data:
                    return await self.async_create_or_update_entry(data=data)
            except AuthError:
                errors["base"] = "not_logged_in"
                _LOGGER.error("Not logged in with one time password")
            except Exception as e:
                errors["base"] = "unknown"
                _LOGGER.exception("Unknown error with one time password")
        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema(
                {vol.Required("code"): str}
            ),
            errors=errors,
        )

    async def async_get_entry_data(self, client, errors):
        try:
            await client.auth.login(self.user_info["username"], self.user_info["password"], self.otp_info["code"])
            id_info = await client.auth.get_id_info()
            return {
                "tokens": client.auth.get_tokens(),
                "email": id_info["email"],
                "username": self.user_info["username"],
                "password": self.user_info["password"],
            }
        except AuthError:
            errors["base"] = "otp_not_logged_in"
            _LOGGER.error("Invalid Verification Code")
        except Exception as e:
            errors["base"] = "unknown"
            _LOGGER.exception("Unknown error")

    async def async_create_or_update_entry(self, data):
        existing_entry = await self.async_set_unique_id(f"{DOMAIN}:{data['email']}")
        if existing_entry:
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        return self.async_create_entry(title=data["email"], data=data)

    async def async_step_reauth(self, data):
        return await self.async_step_user()


class ToyotaNAOptionsFlow(config_entries.OptionsFlow):
    """Lets a config entry's account exclude specific vehicles it can see.

    Mainly for accounts that share a vehicle with another Toyota account (Toyota "family
    sharing") that's also set up as its own config entry in this Home Assistant instance --
    excluding the shared vehicle here lets the other account's entry manage it instead, without
    the two entries ever contending over the same vehicle (see async_claim_vehicles() in
    __init__.py, which enforces this even if a vehicle isn't explicitly excluded here).
    """

    async def async_step_init(self, user_input=None):
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        client = entry_data.get("toyota_na_client") if entry_data else None
        if client is None:
            # The entry has to actually be loaded (logged in) for us to have a client to ask
            # Toyota for this account's vehicle list.
            return self.async_abort(reason="entry_not_loaded")

        try:
            api_vehicles = await client.get_user_vehicle_list()
        except Exception:
            _LOGGER.exception("Failed to fetch vehicle list for options flow")
            return self.async_abort(reason="cannot_fetch_vehicles")

        supported_generations = {item.value for item in ApiVehicleGeneration}
        vehicle_choices = {
            v["vin"]: f"{v.get('modelYear', '')} {v.get('modelName', v['vin'])}".strip()
            for v in api_vehicles
            if "vin" in v and v.get("generation") in supported_generations
        }

        if not vehicle_choices:
            return self.async_abort(reason="no_vehicles")

        if user_input is not None:
            managed = set(user_input.get(CONF_MANAGED_VINS, []))
            excluded_vins = [vin for vin in vehicle_choices if vin not in managed]
            return self.async_create_entry(
                title="", data={OPT_EXCLUDED_VINS: excluded_vins}
            )

        currently_excluded = set(self.config_entry.options.get(OPT_EXCLUDED_VINS, []))
        default_managed = [vin for vin in vehicle_choices if vin not in currently_excluded]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MANAGED_VINS, default=default_managed
                    ): cv.multi_select(vehicle_choices),
                }
            ),
        )
