import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.persistent_notification import async_create

from .sensor import ProxmoxVMStatusSensor
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Sensor- und Binary-Sensor-Plattformen laden
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as e:
        _LOGGER.exception("Plattform-Setup fehlgeschlagen: %s", e)
        return False

    # Benutzerbenachrichtigung nach erfolgreichem Setup
    await async_create(
        hass,
        "DataCenter Assistant wurde über die UI konfiguriert!",
        title="DataCenter Assistant"
    )

    _LOGGER.info("DataCenter Assistant setup_entry wurde erfolgreich ausgeführt.")

    # VM reboot service
    async def reboot_vm_service(call):
        sensor = hass.data.get("datacenter_assistant_sensors", {}).get(entry.entry_id)
        if isinstance(sensor, ProxmoxVMStatusSensor):
            await sensor.reboot_vm()
            _LOGGER.info("Reboot command sent to VM.")
        else:
            _LOGGER.warning("Kein gültiger Proxmox-Sensor gefunden.")

    hass.services.async_register(DOMAIN, "reboot_vm", reboot_vm_service)

    # VCF-Upgrade-Service (nur aktiv, wenn gültige Daten vorhanden)
    async def trigger_upgrade_service(call):
        url = entry.data.get("vcf_url") + "/api/v1/lifecycle/upgrade"
        token = entry.data.get("vcf_token")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        session = async_get_clientsession(hass)
        try:
            async with session.post(url, headers=headers, ssl=False, timeout=10) as resp:
                resp.raise_for_status()
                _LOGGER.info("VCF Upgrade erfolgreich ausgelöst.")
        except Exception as e:
            _LOGGER.error("VCF Upgrade fehlgeschlagen: %s", e)

    hass.services.async_register(DOMAIN, "trigger_upgrade", trigger_upgrade_service)

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
        await async_create(
            hass,
            "Dies ist eine Notification von DataCenter Assistant!",
            title="DataCenter Assistant"
        )
        _LOGGER.info("Notification wurde gesendet.")

    hass.services.async_register(DOMAIN, "notify", handle_notify_service)

    _LOGGER.info("DataCenter Assistant wurde erfolgreich geladen.")
    return True
