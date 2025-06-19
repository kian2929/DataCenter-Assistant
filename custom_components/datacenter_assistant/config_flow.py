from homeassistant import config_entries
import voluptuous as vol
import logging
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate VCF configuration
            required_fields = {
                "vcf_url": "missing_vcf_url",
                "vcf_username": "missing_vcf_username", 
                "vcf_password": "missing_vcf_password"
            }
            
            for field, error_key in required_fields.items():
                if not user_input.get(field, "").strip():
                    errors[field] = error_key
                    break
            
            if not errors:
                return self.async_create_entry(title="DataCenter Assistant", data=user_input)

        # Show the form with any errors
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("vcf_url"): str,
                vol.Required("vcf_username"): str,
                vol.Required("vcf_password"): str,
            }),
            errors=errors
        )
