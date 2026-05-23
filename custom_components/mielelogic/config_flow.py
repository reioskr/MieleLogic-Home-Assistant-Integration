"""Config flow for Miele Logic integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import MieleLogicAPI
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_COUNTRY

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_COUNTRY, default="dk"): vol.In(
            {"dk": "Denmark", "se": "Sweden", "no": "Norway", "fi": "Finland", "de": "Germany"}
        ),
    }
)


class MieleLogicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Miele Logic."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = MieleLogicAPI(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                country=user_input[CONF_COUNTRY],
            )

            valid = await self.hass.async_add_executor_job(api.test_connection)
            if valid:
                # Get account info for the title
                account = await self.hass.async_add_executor_job(api.get_account)
                name = account.get("Cards", [{}])[0].get("Name", user_input[CONF_USERNAME])

                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"MieleLogic - {name}",
                    data=user_input,
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
