from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

# Import DOMAIN from __init__.py
from . import DOMAIN

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate VCF configuration
            vcf_url = user_input.get("vcf_url", "").strip()
            vcf_username = user_input.get("vcf_username", "").strip()
            vcf_password = user_input.get("vcf_password", "").strip()
            
            if not vcf_url:
                errors["vcf_url"] = "missing_vcf_url"
            elif not vcf_username:
                errors["vcf_username"] = "missing_vcf_username"
            elif not vcf_password:
                errors["vcf_password"] = "missing_vcf_password"
            
            if not errors:
                return self.async_create_entry(title="DataCenter Assistant", data=user_input)

        # Show the form with all required fields
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("vcf_url"): str,
                vol.Required("vcf_username"): str,
                vol.Required("vcf_password"): str,
            }),
            errors=errors
        )
