"""DataCenter Assistant Integration."""

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    # Initialize hass.data[DOMAIN] if it doesn't exist
    hass.data.setdefault(DOMAIN, {})
    # You can store entry-specific data here if needed, e.g., hass.data[DOMAIN][entry.entry_id] = {}

    hass.components.persistent_notification.create(
        f"DataCenter Assistant wurde über die UI konfiguriert!",
        title="DataCenter Assistant"
    )
    _LOGGER.info("DataCenter Assistant setup_entry wurde erfolgreich aufgerufen.")

    # Forward the setup to the sensor platform and await its completion
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )

    # Ensure domain and entry_id exist before popping
    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Optionally remove the domain key if it's now empty
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_setup(hass, config):
    """Set up the DataCenter Assistant component."""

    async def handle_notify_service(call):
        """Handle the notify service call."""
        hass.components.persistent_notification.create(
            "Dies ist eine Notification von DataCenter Assistant!",
            title="DataCenter Assistant"
        )
        _LOGGER.info("Notification wurde gesendet.")

    # Deinen Notify-Service registrieren
    hass.services.async_register(DOMAIN, "notify", handle_notify_service)

    _LOGGER.info("DataCenter Assistant wurde erfolgreich geladen!")
    return True
