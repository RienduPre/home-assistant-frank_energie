"""Config flow for Frank Energie integration."""
import logging
from collections.abc import Mapping
from typing import Any, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_AUTHENTICATION,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult
from python_frank_energie import FrankEnergie
from python_frank_energie.exceptions import AuthException

from .const import DOMAIN
from .api import FrankEnergieAPI

_LOGGER: logging.Logger = logging.getLogger(__package__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Frank Energie."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: dict[str, str] = {}
        self._reauth_entry: Optional[config_entries.ConfigEntry] = None

    async def async_step_login(
        self, user_input: Optional[dict[str, Any]] = None, errors=None
    ) -> FlowResult:
        """Handle login with credentials by user."""
        if not user_input:
            username = (
                self._reauth_entry.data[CONF_USERNAME]
                if self._reauth_entry
                else None
            )

            data_schema = vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=username): vol.Coerce(str),
                    vol.Required(CONF_PASSWORD): vol.Coerce(str),
                }
            )

            return self.async_show_form(
                step_id="login",
                data_schema=data_schema,
                errors=errors,
            )

        errors = self._validate_login_input(user_input)

        if errors:
            return self._show_login_form(errors=errors)

        # Create an instance of the FrankEnergieAPI class
        api = FrankEnergie()

        try:
            # Authenticate with Frank Energie API
            auth = await api.login(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
        except AuthException:
            _LOGGER.exception("Error during login")
            return await self.async_step_login(errors={"base": "invalid_auth"})

        data = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_ACCESS_TOKEN: auth.authToken,
            CONF_TOKEN: auth.refreshToken,
        }

        # Check if a refresh token is available
        if self._reauth_entry and CONF_TOKEN in self._reauth_entry.data:
            # Use the refresh token to get a new auth token
            async with FrankEnergie() as api:
                try:
                    # Save the credentials to the config entry's data
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data=data,
                    )

                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                    )

                    return self.async_abort(reason="reauth_successful")
                except AuthException as ex:
                    _LOGGER.exception("Error during login", exc_info=ex)
                    return await self.async_step_login(errors={"base": "invalid_auth"})
        else:
            # Perform the initial login
            async with FrankEnergie() as api:
                try:
                    auth = await api.login(
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )
                except AuthException as ex:
                    _LOGGER.exception("Error during login", exc_info=ex)
                    return await self.async_step_login(errors={"base": "invalid_auth"})

        data = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_ACCESS_TOKEN: auth.authToken,
            CONF_TOKEN: auth.refreshToken,
        }

        if self._reauth_entry:
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data=data,
            )

            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            )

            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id(user_input[CONF_USERNAME])
        self._abort_if_unique_id_configured()

        return await self._async_create_entry(data)

    async def async_step_user(
        self, user_input=None, errors=None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        #if not user_input:
        if user_input is None:
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_AUTHENTICATION, default=True): bool,
                }
            )

            return self.async_show_form(
                step_id="user",
                data_schema=data_schema,
                errors=errors,
            )

        if user_input[CONF_AUTHENTICATION]:
            return await self.async_step_login()

        data = {}

        return await self._async_create_entry(data)

    async def _show_config_form(self) -> FlowResult:
        """Show the configuration form to edit login information."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME): str,
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=self._errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Handle configuration by re-auth."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_login()

    async def _async_create_entry(self, data):
        unique_id = data.get(CONF_USERNAME, "frank_energie")
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        entry_data = {
            CONF_USERNAME: data.get(CONF_USERNAME),
            CONF_ACCESS_TOKEN: data.get(CONF_ACCESS_TOKEN),
            CONF_TOKEN: data.get(CONF_TOKEN),
        }

        if self._reauth_entry:
            self.hass.config_entries.async_update_entry(
                self._reauth_entry, data=entry_data
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            )
            return self.async_abort(reason="reauth_successful")

        if CONF_TOKEN in data:
            entry_data[CONF_TOKEN] = data[CONF_TOKEN]

        return self.async_create_entry(
            title=data.get(CONF_USERNAME, "Frank Energie"), data=entry_data
        )

    def _show_user_form(self, errors: Optional[dict[str, str]] = None) -> FlowResult:
        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_AUTHENTICATION, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    def _show_login_form(self, errors: Optional[dict[str, str]] = None) -> FlowResult:
        username = (
            self._reauth_entry.data[CONF_USERNAME]
            if self._reauth_entry
            else None
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=username): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="login",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return FrankEnergieOptionsFlowHandler(config_entry)

    @staticmethod
    def _validate_login_input(user_input: dict[str, Any]) -> dict[str, str]:
        errors = {}
        if user_input[CONF_USERNAME].strip() == "":
            errors[CONF_USERNAME] = "Username is required."
        if user_input[CONF_PASSWORD].strip() == "":
            errors[CONF_PASSWORD] = "Password is required."
        return errors
    
class FrankEnergieOptionsFlowHandler(config_entries.OptionsFlow):
    """Frank Energie config flow options handler."""

    def __init__(self, config_entry):
        """Initialize Frank Energie options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None, errors=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        username = (
            self.config_entry.data.get(CONF_USERNAME)
            if self.config_entry
            else None
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_USERNAME),
            data=self.options,
        )