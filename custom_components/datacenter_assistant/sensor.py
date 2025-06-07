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

# DOMAIN-Definition entfernen und stattdessen hier eine lokale Variable verwenden
_DOMAIN = "datacenter_assistant"

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    sensor = ProxmoxVMStatusSensor(hass, entry)
    entities = [sensor]

    # Save the sensor instance for reboot
    hass.data[_DOMAIN] = hass.data.get(_DOMAIN, {})
    hass.data[_DOMAIN]["sensors"] = hass.data.get(_DOMAIN, {}).get("sensors", {})
    hass.data[_DOMAIN]["sensors"][entry.entry_id] = sensor

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
        entities.append(VCFAvailableUpdatesSensor(coordinator))  # Neuen Sensor hinzufügen

    except Exception as e:
        _LOGGER.warning("VCF part could not be initialized: %s", e)

    async_add_entities(entities, True)

    # Koordinator in der Hauptdomain speichern für andere Komponenten
    hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator


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
        """Return the state of the VM."""
        # Ursprüngliche Implementierung wiederherstellen
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
        if self.state == "upgrades_available":
            return "mdi:update"
        elif self.state == "up_to_date":
            return "mdi:check-circle"
        else:
            return "mdi:sync-alert"

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            # Prüfen, ob es eine erfolgreiche API-Antwort gab
            if self.coordinator.data is not None:
                # Nur bei Bedarf detaillierter loggen
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(f"VCF data: {self.coordinator.data}")
                
                # Wenn upgradable_data vorhanden ist, haben wir eine Verbindung
                if "upgradable_data" in self.coordinator.data:
                    data = self.coordinator.data.get("upgradable_data", {})
                    elements = data.get("elements", [])
                    
                    # Nach verfügbaren Updates suchen
                    for item in elements:
                        if item.get("status") == "AVAILABLE":
                            _LOGGER.info("VCF Updates sind verfügbar")
                            return "upgrades_available"
                    
                    # Verbunden, aber keine Updates verfügbar
                    return "up_to_date"
            
        # Keine Daten oder Fehler bei der Anfrage
        except Exception as e:
            _LOGGER.error(f"Error checking VCF upgrade status: {e}")
        
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
        
    @property
    def extra_state_attributes(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            statuses = {}
            
            # Zähle die verschiedenen Status-Typen
            for item in data:
                status = item.get("status", "UNKNOWN")
                if status not in statuses:
                    statuses[status] = 0
                statuses[status] += 1
            
            # Stelle sicher, dass alle erwarteten Status vorhanden sind
            for status in ["AVAILABLE", "PENDING", "SCHEDULED", "FAILED"]:
                if status not in statuses:
                    statuses[status] = 0
                    
            return statuses
        except Exception as e:
            _LOGGER.warning("Error extracting VCF distribution attributes: %s", e)
            return {}

        
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


class VCFAvailableUpdatesSensor(CoordinatorEntity, SensorEntity):
    """Sensor that lists all available VCF updates."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "VCF Available Updates"
        self._attr_unique_id = "vcf_available_updates"
        self._attr_icon = "mdi:format-list-bulleted"
        self.coordinator = coordinator

    @property
    def state(self):
        """Return the count of available updates."""
        try:
            if self.coordinator.data and "upgradable_data" in self.coordinator.data:
                elements = self.coordinator.data["upgradable_data"].get("elements", [])
                available_updates = [item for item in elements if item.get("status") == "AVAILABLE"]
                return len(available_updates)
            return 0
        except Exception as e:
            _LOGGER.error(f"Error counting VCF updates: {e}")
            return 0
    
    @property
    def extra_state_attributes(self):
        """Return details about available updates."""
        try:
            if self.coordinator.data and "upgradable_data" in self.coordinator.data:
                elements = self.coordinator.data["upgradable_data"].get("elements", [])
                
                # Nach Status gruppieren
                available_updates = []
                pending_updates = []
                scheduled_updates = []
                
                for update in elements:
                    resource = update.get("resource", {})
                    update_info = {
                        "component_type": resource.get("type", "Unknown"),
                        "fqdn": resource.get("fqdn", "Unknown"),
                        "description": update.get("description", ""),
                        "status": update.get("status", "")
                    }
                    
                    if update.get("status") == "AVAILABLE":
                        available_updates.append(update_info)
                    elif update.get("status") == "PENDING":
                        pending_updates.append(update_info)
                    elif update.get("status") == "SCHEDULED":
                        scheduled_updates.append(update_info)
                
                return {
                    "available_updates": available_updates,
                    "pending_updates": pending_updates,
                    "scheduled_updates": scheduled_updates,
                    "available_count": len(available_updates),
                    "pending_count": len(pending_updates),
                    "scheduled_count": len(scheduled_updates)
                }
            return {
                "available_updates": [],
                "pending_updates": [], 
                "scheduled_updates": [],
                "available_count": 0,
                "pending_count": 0,
                "scheduled_count": 0
            }
        except Exception as e:
            _LOGGER.error(f"Error getting VCF update details: {e}")
            return {
                "error": str(e),
                "available_updates": [],
                "pending_updates": [],
                "scheduled_updates": [],
                "available_count": 0,
                "pending_count": 0,
                "scheduled_count": 0
            }

