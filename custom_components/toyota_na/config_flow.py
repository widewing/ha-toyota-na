import logging

from homeassistant import config_entries
import voluptuous as vol

from toyota_na import ToyotaOneAuth, ToyotaOneClient
from toyota_na.exceptions import AuthError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ToyotaNAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Toyota (North America) connected services"""
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = await self.async_get_entry_data(user_input, errors)
            if data:
                return await self.async_create_or_update_entry(data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str
            }),
            errors=errors
        )

    async def async_get_entry_data(self, user_input, errors):
        try:
            client = ToyotaOneClient()
            await client.auth.login(user_input["username"], user_input["password"])
            id_info = await client.auth.get_id_info()
            return {
                "tokens": client.auth.get_tokens(),
                "email": id_info["email"],
                "username": user_input["username"],
                "password": user_input["password"]
            }
        except AuthError:
            errors["base"] = "not_logged_in"
            _LOGGER.error("Not logged in")
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
