from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "datacenter_assistant"

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Basic validation
            if user_input.get("vcf_url") and not user_input.get("vcf_token"):
                errors["vcf_token"] = "missing_vcf_token"
            elif user_input.get("vcf_token") and not user_input.get("vcf_url"):
                errors["vcf_url"] = "missing_vcf_url"
            
            if not errors:
                return self.async_create_entry(title="DataCenter Assistant", data=user_input)

        # Show the form with any errors
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("ip_address"): str,
                vol.Required("port", default=8006): int,
                vol.Required("api_token_id"): str,
                vol.Required("api_token_secret"): str,
                vol.Required("node"): str,
                vol.Required("vmid"): int,
                vol.Optional("vcf_url", default=""): str,
                vol.Optional("vcf_token", default=""): str,
            }),
            errors=errors
        )
