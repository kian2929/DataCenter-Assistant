"""Config flow for DataCenter Assistant."""
from homeassistant import config_entries
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "datacenter_assistant"

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="DataCenter Assistant", data={})

        return self.async_show_form(step_id="user")
