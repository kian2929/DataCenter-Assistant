import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
from aiohttp import ClientError
import asyncio
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    sensor = ProxmoxVMStatusSensor(hass, entry)

    # Optional: Upgrade-Daten von neuem Coordinator laden
    #test
    coordinator = get_coordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Zusätzliche VCF-Sensoren hinzufügen
    upgrade_status_sensor = VCFUpgradeStatusSensor(coordinator)
    upgrade_graph_sensor = VCFUpgradeGraphSensor(coordinator)

    async_add_entities([sensor, upgrade_status_sensor, upgrade_graph_sensor], True)

    # Save the Proxmox sensor for reboot
    hass.data["datacenter_assistant_sensors"] = hass.data.get("datacenter_assistant_sensors", {})
    hass.data["datacenter_assistant_sensors"][entry.entry_id] = sensor


class ProxmoxVMStatusSensor(SensorEntity):
    """Representation of a Proxmox VM Status Sensor."""

    def __init__(self, hass, entry):
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._state = STATE_UNKNOWN
        self._attr_name = "Proxmox VM Status"
        self._attr_unique_id = "proxmox_vm_status"

    @property
    def state(self):
        """Return the state of the VM."""
        return self._state

    @property
    def icon(self):
        """Return the icon depending on the state."""
        if self._state == "running":
            return "mdi:server-network"
        elif self._state == "stopped":
            return "mdi:server-network-off"
        else:
            return "mdi:server"

    async def async_update(self):
        """Fetch new state data for the VM."""
        ip_address = self._entry.data.get("ip_address")
        port = self._entry.data.get("port")
        api_token_id = self._entry.data.get("api_token_id")
        api_token_secret = self._entry.data.get("api_token_secret")
        node = self._entry.data.get("node")
        vmid = self._entry.data.get("vmid")

        url = f"https://{ip_address}:{port}/api2/json/nodes/{node}/qemu/{vmid}/status/current"
        headers = {
            "Authorization": f"PVEAPIToken={api_token_id}={api_token_secret}"
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

                status = data["data"].get("status", None)
                if status:
                    self._state = status
                    _LOGGER.info("Proxmox VM Status: %s", self._state)
                else:
                    self._state = STATE_UNKNOWN
                    _LOGGER.warning("Proxmox API returned no status.")

        except (ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Connection error: %s", e)
            self._state = STATE_UNKNOWN
        except Exception as e:
            _LOGGER.exception("Unexpected error: %s", e)
            self._state = STATE_UNKNOWN

    async def reboot_vm(self):
        """Reboot the VM."""
        ip_address = self._entry.data.get("ip_address")
        port = self._entry.data.get("port")
        api_token_id = self._entry.data.get("api_token_id")
        api_token_secret = self._entry.data.get("api_token_secret")
        node = self._entry.data.get("node")
        vmid = self._entry.data.get("vmid")

        if not node or vmid is None:
            _LOGGER.error("Missing node or vmid in config entry: node=%s, vmid=%s", node, vmid)
            self._state = STATE_UNKNOWN
            return

        url = f"https://{ip_address}:{port}/api2/json/nodes/{node}/qemu/{vmid}/status/reboot"
        headers = {
            "Authorization": f"PVEAPIToken={api_token_id}={api_token_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.post(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                _LOGGER.info("Successfully sent reboot command to VM %s", vmid)

        except (ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("Connection error while rebooting VM: %s", e)
        except Exception as e:
            _LOGGER.exception("Unexpected error while rebooting VM: %s", e)


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
        status_counts = {}
        for item in self.coordinator.data["upgradable_data"]["elements"]:
            status = item["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        return status_counts

