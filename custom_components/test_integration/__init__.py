"""Init file for Test-Integration."""
DOMAIN = "test_integration"

async def async_setup_entry(hass, config_entry):
    """Set up Test Integration from a config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "button")
    )
    return True
