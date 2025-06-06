import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
from aiohttp import ClientError
import asyncio
from .coordinator import get_coordinator
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    sensor = ProxmoxVMStatusSensor(hass, entry)
    entities = [sensor]

    # Save the sensor instance for reboot
    hass.data["datacenter_assistant_sensors"] = hass.data.get("datacenter_assistant_sensors", {})
    hass.data["datacenter_assistant_sensors"][entry.entry_id] = sensor

    # Optional: Add VCF sensors if they can be initialized
    try:
        coordinator = get_coordinator(hass, entry)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:
            _LOGGER.warning("VCF coordinator first refresh failed: %s", e)

        entities.append(VCFUpgradeStatusSensor(coordinator))
        entities.append(VCFUpgradeGraphSensor(coordinator))
        entities.append(VCFUpgradeComponentsSensor(coordinator))

    except Exception as e:
        _LOGGER.warning("VCF part could not be initialized: %s", e)

    async_add_entities(entities, True)


class ProxmoxVMStatusSensor(SensorEntity):
    """Representation of a Proxmox VM Status Sensor."""

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
        else:
            return "mdi:server"

    async def async_update(self):
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


class VCFUpgradeStatusSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrade Status"
        self._attr_unique_id = "vcf_upgrade_status"

    @property
    def icon(self):
        state = self.state
        if state == "upgrades_available":
            return "mdi:update"
        elif state == "up_to_date":
            return "mdi:check-circle"
        else:
            return "mdi:cloud-off-outline"

    @property
    def state(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", None)

            # Kein Zugriff oder kein Feld "elements"
            if data is None:
                return "not_connected"

            # Zugriff möglich, aber Liste ist leer
            if isinstance(data, list) and len(data) == 0:
                return "not_connected"

            # Prüfen ob verfügbare Upgrades enthalten sind
            upgrades = [b for b in data if b.get("status") == "AVAILABLE"]
            return "upgrades_available" if upgrades else "up_to_date"

        except Exception as e:
            _LOGGER.warning("Error determining VCF upgrade status: %s", e)
            return "not_connected"

    @property
    def extra_state_attributes(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return {
                "available_count": len([x for x in data if x.get("status") == "AVAILABLE"]),
                "pending_count": len([x for x in data if x.get("status") == "PENDING"]),
                "scheduled_count": len([x for x in data if x.get("status") == "SCHEDULED"]),
                "raw_statuses": [x.get("status") for x in data],
                "connection_error": str(self.coordinator.last_exception) if self.coordinator.last_exception else None,
            }
        except Exception as e:
            _LOGGER.warning("Error extracting VCF attributes: %s", e)
            return {"error": str(e)}


class VCFUpgradeGraphSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrade Distribution"
        self._attr_unique_id = "vcf_upgrade_distribution"

    @property
    def icon(self):
        return "mdi:chart-pie"

    @property
    def state(self):
        return "ok"
        
class VCFUpgradeComponentsSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrade Components"
        self._attr_unique_id = "vcf_upgrade_components"


    @property
    def state(self):
        return "ok"

    @property
    def extra_state_attributes(self):
        try:
            components = {}
            for item in self.coordinator.data.get("upgradable_data", {}).get("elements", []):
                resource = item.get("resource", {})
                fqdn = resource.get("fqdn", "unknown")
                status = item.get("status", "unknown")
                components[fqdn] = status
            return {"components": components}
        except Exception as e:
            _LOGGER.warning("Error building VCF component list: %s", e)
            return {"components": {}}

