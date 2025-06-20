from homeassistant import config_entries
import voluptuous as vol
import logging
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

class DataCenterAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DataCenter Assistant."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("DataCenter Assistant config flow started")
        errors = {}
        
        if user_input is not None:
            _LOGGER.info("Processing DataCenter Assistant configuration submission")
            _LOGGER.debug(f"Received config data with URL: {user_input.get('vcf_url', 'NOT_PROVIDED')}")
            
            # Validate VCF configuration
            required_fields = {
                "vcf_url": "missing_vcf_url",
                "vcf_username": "missing_vcf_username", 
                "vcf_password": "missing_vcf_password"
            }
            
            for field, error_key in required_fields.items():
                if not user_input.get(field, "").strip():
                    _LOGGER.warning(f"Missing required field: {field}")
                    errors[field] = error_key
                    break
            
            if not errors:
                _LOGGER.info("DataCenter Assistant configuration validation successful")
                _LOGGER.debug(f"Creating config entry for VCF URL: {user_input.get('vcf_url')}")
                return self.async_create_entry(title="DataCenter Assistant", data=user_input)
            else:
                _LOGGER.warning(f"Configuration validation failed with errors: {list(errors.keys())}")

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
