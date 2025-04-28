"""Config flow for DataCenter Assistant."""

from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "datacenter_assistant"

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            # Eingaben speichern
            return self.async_create_entry(title="DataCenter Assistant", data=user_input)

        # Formular anzeigen
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("ip_address", description=""): str,
                vol.Required("port", default=8006, description=""): int,
                vol.Required("api_token_id", description=""): str,
                vol.Required("api_token_secret", description=""): str,
            }),
            description_placeholders={
                "ip_address": "",
                "port": "",
                "api_token_id": "",
                "api_token_secret": "",
            }
        )
