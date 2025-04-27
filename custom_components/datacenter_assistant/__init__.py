"""DataCenter Assistant Integration."""

import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Set up DataCenter Assistant from a config entry."""
    hass.components.persistent_notification.create(
        f"DataCenter Assistant wurde über die UI konfiguriert!",
        title="DataCenter Assistant"
    )
    _LOGGER.info("DataCenter Assistant setup_entry wurde erfolgreich aufgerufen.")
    return True


async def async_setup(hass, config):
    """Set up the DataCenter Assistant component."""

    async def handle_notify_service(call):
        """Handle the notify service call."""
        hass.components.persistent_notification.create(
            "Dies ist eine Notification von DataCenter Assistant!",
            title="DataCenter Assistant"
        )
        _LOGGER.info("Notification wurde gesendet.")

    hass.services.async_register("datacenter_assistant", "notify", handle_notify_service)

    _LOGGER.info("DataCenter Assistant wurde erfolgreich geladen!")
    return True

