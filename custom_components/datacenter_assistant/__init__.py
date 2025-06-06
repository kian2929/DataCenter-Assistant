import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .sensor import async_setup_entry as setup_sensor

_LOGGER = logging.getLogger(__name__)

DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor"]  # Add binary_sensor to platforms

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Configure logging
    logging.getLogger('custom_components.datacenter_assistant').setLevel(logging.DEBUG)
    
    # Setup platforms
    for platform in PLATFORMS:
        try:
            await hass.config_entries.async_forward_entry_setup(entry, platform)
        except Exception as e:
            _LOGGER.error(f"Error setting up {platform} platform: {e}")
    
    # Register services
    async def reboot_vm_service(call):
        """Handle reboot_vm service call."""
        sensor = hass.data.get("datacenter_assistant_sensors", {}).get(entry.entry_id)
        if sensor:
            await sensor.reboot_vm()
            _LOGGER.info("Reboot command sent to VM.")
        else:
            _LOGGER.error("No valid ProxmoxVMStatusSensor found to reboot.")

    hass.services.async_register(
        DOMAIN,
        "reboot_vm",
        reboot_vm_service,
    )

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
