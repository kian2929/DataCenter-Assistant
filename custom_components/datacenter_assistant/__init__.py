import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .sensor import async_setup_entry as setup_sensor
from homeassistant.components.button import ButtonEntity
import homeassistant.helpers.entity_platform as platform

_LOGGER = logging.getLogger(__name__)
_LOGGER.debug("Initialized with log handlers: %s", logging.getLogger().handlers)

DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor", "button"]  # Button-Plattform hinzufügen

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Configure logging
    logging.getLogger('custom_components.datacenter_assistant').setLevel(logging.CRITICAL)
    
    # Log integration loading
    _LOGGER.debug("DataCenter Assistant integration loaded")
    
    # Setup platforms
    for platform in PLATFORMS:
        try:
            await hass.config_entries.async_forward_entry_setups(entry, [platform])
        except Exception as e:
            _LOGGER.error(f"Error setting up {platform} platform: {e}")
    
    # Register services - existierende Services beibehalten...
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(*[
            hass.config_entries.async_forward_entry_unload(entry, platform)
            for platform in PLATFORMS
        ])
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_setup(hass: HomeAssistant, config):
    """Set up the component (optional)."""
    return True
