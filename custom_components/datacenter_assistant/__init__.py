"""DataCenter Assistant Integration."""

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .sensor import async_setup_entry as setup_sensor
from .binary_sensor import async_setup_entry as setup_binary_sensor
from .button import async_setup_entry as setup_button
from .sensor import ProxmoxVMStatusSensor
from .coordinator import get_coordinator


_LOGGER = logging.getLogger(__name__)
DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Set up sensors (Proxmox + VCF)
    await setup_sensor(hass, entry, async_add_entities=None)

    # Optional: weitere Komponenten einrichten, wenn vorhanden
    try:
        await setup_binary_sensor(hass, entry, async_add_entities=None)
    except Exception:
        _LOGGER.debug("No binary_sensor.py loaded or setup failed – skipping.")

    try:
        await setup_button(hass, entry, async_add_entities=None)
    except Exception:
        _LOGGER.debug("No button.py loaded or setup failed – skipping.")

    hass.components.persistent_notification.create(
        f"DataCenter Assistant wurde über die UI konfiguriert!",
        title="DataCenter Assistant"
    )
    _LOGGER.info("DataCenter Assistant setup_entry wurde erfolgreich aufgerufen.")

    # Optional: reboot service
    async def reboot_vm_service(call):
        sensor = hass.data.get("datacenter_assistant_sensors", {}).get(entry.entry_id)
        if isinstance(sensor, ProxmoxVMStatusSensor):
            await sensor.reboot_vm()
            _LOGGER.info("Reboot command sent to VM.")
        else:
            _LOGGER.error("No valid ProxmoxVMStatusSensor found to reboot.")

    hass.services.async_register(DOMAIN, "reboot_vm", reboot_vm_service)

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
