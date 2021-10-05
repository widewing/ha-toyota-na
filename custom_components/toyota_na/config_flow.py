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
            try:
                client = ToyotaOneClient()
                await client.auth.login(user_input["authorization_code"])
                id_info = await client.auth.get_id_info()
                return self.async_create_entry(
                    title=id_info["email"],
                    data={
                        "tokens": client.auth.get_tokens(),
                        "email": id_info["email"]
                    }
                )
            except NotLoggedIn:
                errors["base"] = "not_logged_in"
                _LOGGER.error("Not logged in")
            except Exception as e:
                errors["base"] = "unknown"
                _LOGGER.exception("Unknown error")
                
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("authorization_code"): str}),
            errors=errors
        )

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     return ToyotaNAOptionsFlowHandler(config_entry)


# class ToyotaNAOptionsFlowHandler(config_entries.OptionsFlow):
#     """Config flow options handler for Toyota Connected Services."""

#     def __init__(self, config_entry):
#         """Initialize options flow."""
#         self.config_entry = config_entry
#         # Cast from MappingProxy to dict to allow update.
#         self.options = dict(config_entry.options)

#     async def async_step_init(self, user_input=None):
#         """Manage the options."""
#         if user_input is not None:
#             try:
#                 client = ToyotaOneClient()
#                 await client.auth.login(user_input["authorization_code"])
#                 id_info = await client.auth.get_id_info()
#                 return self.async_create_entry(
#                     title=id_info["email"],
#                     data={
#                         "tokens": client.auth.get_tokens(),
#                         "email": id_info["email"]
#                     }
#                 )
#             except NotLoggedIn:
#                 errors["base"] = "not_logged_in"
#                 _LOGGER.error("Not logged in")
#             except Exception as e:
#                 errors["base"] = "unknown"
#                 _LOGGER.exception("Unknown error")
                
#         return self.async_show_form(
#             step_id="init",
#             data_schema=vol.Schema({vol.Required("authorization_code"): str}),
#             errors=errors
#         )