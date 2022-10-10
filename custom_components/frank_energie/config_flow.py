"""Config flow for Picnic integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from .const import COMPONENT_TITLE, DOMAIN, UNIQUE_ID

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(ConfigEntry.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Frank Energie."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle adding the config, no user input is needed."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=None
            )

        # Abort if we're adding a new config and the unique id is already in use, else create the entry
        # For now it's only possible to add the Frank Energie integration once
        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=COMPONENT_TITLE, data={})
