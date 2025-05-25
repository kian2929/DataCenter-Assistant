import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .sensor import async_setup_entry as setup_sensor
from .coordinator import get_coordinator
from .sensor import ProxmoxVMStatusSensor

_LOGGER = logging.getLogger(__name__)
DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Set up sensors
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])

    # Optional: binary_sensor or button can be added similarly

    from homeassistant.components.persistent_notification import async_create
    await async_create(hass, "DataCenter Assistant wurde über die UI konfiguriert!", title="DataCenter Assistant")

    _LOGGER.info("DataCenter Assistant setup_entry wurde erfolgreich aufgerufen.")

    # Reboot VM Service
    async def reboot_vm_service(call):
        sensor = hass.data.get("datacenter_assistant_sensors", {}).get(entry.entry_id)
        if isinstance(sensor, ProxmoxVMStatusSensor):
            await sensor.reboot_vm()
            _LOGGER.info("Reboot command sent to VM.")
        else:
            _LOGGER.error("No valid ProxmoxVMStatusSensor found to reboot.")

    hass.services.async_register(DOMAIN, "reboot_vm", reboot_vm_service)

    # Trigger VCF Upgrade Service
    async def trigger_upgrade_service(call):
        url = "https://vcf.example.local/api/v1/lifecycle/upgrade"
        headers = {
            "Authorization": "Bearer DEIN_TOKEN",
            "Content-Type": "application/json"
        }
        session = async_get_clientsession(hass)
        try:
            async with session.post(url, headers=headers, ssl=False, timeout=10) as resp:
                resp.raise_for_status()
                _LOGGER.info("VCF Upgrade erfolgreich ausgelöst.")
        except Exception as e:
            _LOGGER.error("VCF Upgrade fehlgeschlagen: %s", e)

    hass.services.async_register(
        DOMAIN,
        "trigger_upgrade",
        trigger_upgrade_service
    )

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

    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_setup(hass, config):
    """Set up the DataCenter Assistant component."""
    async def handle_notify_service(call):
        hass.components.persistent_notification.create(
            "Dies ist eine Notification von DataCenter Assistant!",
            title="DataCenter Assistant"
        )
        _LOGGER.info("Notification wurde gesendet.")

    hass.services.async_register(DOMAIN, "notify", handle_notify_service)

    _LOGGER.info("DataCenter Assistant wurde erfolgreich geladen!")
    return True