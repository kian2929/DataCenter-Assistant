import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
from aiohttp import ClientError
import asyncio
from homeassistant.exceptions import ConfigEntryNotReady
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensor platform for both Proxmox and VCF."""
    try:
        coordinator = get_coordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady from err

    proxmox_sensor = ProxmoxVMStatusSensor(hass, entry)
    upgrade_status_sensor = VCFUpgradeStatusSensor(coordinator)
    upgrade_graph_sensor = VCFUpgradeGraphSensor(coordinator)

    async_add_entities([proxmox_sensor, upgrade_status_sensor, upgrade_graph_sensor], True)

    hass.data["datacenter_assistant_sensors"] = hass.data.get("datacenter_assistant_sensors", {})
    hass.data["datacenter_assistant_sensors"][entry.entry_id] = proxmox_sensor


class ProxmoxVMStatusSensor(SensorEntity):
    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._state = STATE_UNKNOWN
        self._attr_name = "Proxmox VM Status"
        self._attr_unique_id = "proxmox_vm_status"

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        if self._state == "running":
            return "mdi:server-network"
        elif self._state == "stopped":
            return "mdi:server-network-off"
        return "mdi:server"

    async def async_update(self):
        ip = self._entry.data.get("ip_address")
        port = self._entry.data.get("port")
        token_id = self._entry.data.get("api_token_id")
        token_secret = self._entry.data.get("api_token_secret")
        node = self._entry.data.get("node")
        vmid = self._entry.data.get("vmid")

        url = f"https://{ip}:{port}/api2/json/nodes/{node}/qemu/{vmid}/status/current"
        headers = {
            "Authorization": f"PVEAPIToken={token_id}={token_secret}"
        }

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                data = await r.json()
                self._state = data["data"].get("status", STATE_UNKNOWN)
        except (ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Connection error: %s", e)
            self._state = STATE_UNKNOWN
        except Exception as e:
            _LOGGER.exception("Unexpected error: %s", e)
            self._state = STATE_UNKNOWN

    async def reboot_vm(self):
        ip = self._entry.data.get("ip_address")
        port = self._entry.data.get("port")
        token_id = self._entry.data.get("api_token_id")
        token_secret = self._entry.data.get("api_token_secret")
        node = self._entry.data.get("node")
        vmid = self._entry.data.get("vmid")

        if not node or vmid is None:
            _LOGGER.error("Missing node or vmid.")
            return

        url = f"https://{ip}:{port}/api2/json/nodes/{node}/qemu/{vmid}/status/reboot"
        headers = {
            "Authorization": f"PVEAPIToken={token_id}={token_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                _LOGGER.info("Reboot command sent to VM %s", vmid)
        except Exception as e:
            _LOGGER.error("Reboot error: %s", e)


class VCFUpgradeStatusSensor(SensorEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "VCF Upgrade Status"

    @property
    def state(self):
        upgrades = [b for b in self.coordinator.data["upgradable_data"]["elements"] if b["status"] == "AVAILABLE"]
        return "upgrades_available" if upgrades else "up_to_date"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data["upgradable_data"]["elements"]
        return {
            "available_count": len([x for x in data if x["status"] == "AVAILABLE"]),
            "pending_count": len([x for x in data if x["status"] == "PENDING"]),
            "scheduled_count": len([x for x in data if x["status"] == "SCHEDULED"])
        }


class VCFUpgradeGraphSensor(SensorEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "VCF Upgrade Distribution"

    @property
    def state(self):
        return "ok"

    @property
    def extra_state_attributes(self):
        counts = {}
        for item in self.coordinator.data["upgradable_data"]["elements"]:
            status = item["status"]
            counts[status] = counts.get(status, 0) + 1
        return counts
