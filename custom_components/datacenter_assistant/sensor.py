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
    entities = []

    # Initialize VCF coordinator and sensors
    try:
        coordinator = get_coordinator(hass, entry)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:
            _LOGGER.warning("VCF coordinator first refresh failed: %s", e)

        entities.extend([
            VCFUpgradeStatusSensor(coordinator),
            VCFUpgradeGraphSensor(coordinator),
            VCFUpgradeComponentsSensor(coordinator),
            VCFAvailableUpdatesSensor(coordinator)
        ])

        # Store coordinator for other components
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator

    except Exception as e:
        _LOGGER.error("VCF sensors could not be initialized: %s", e)
        # Create empty entities list if VCF setup fails
        entities = []

    async_add_entities(entities, True)


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
    """Sensor that lists all available VCF bundles."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "VCF Available Updates"
        self._attr_unique_id = "vcf_available_updates"
        self._attr_icon = "mdi:package-variant-closed"
        self.coordinator = coordinator

    @property
    def state(self):
        """Return the count of available bundles."""
        try:
            if self.coordinator.data and "bundle_data" in self.coordinator.data:
                bundles = self.coordinator.data.get("bundle_data", {}).get("elements", [])
                return len(bundles)
            return 0
        except Exception as e:
            _LOGGER.error(f"Error counting VCF bundles: {e}")
            return 0
    
    @property
    def extra_state_attributes(self):
        """Return details about available bundles."""
        try:
            result = {
                "bundles": [],
                "bundle_count": 0
            }
            
            # Bundle-Daten verarbeiten
            if self.coordinator.data and "bundle_data" in self.coordinator.data:
                bundles = self.coordinator.data.get("bundle_data", {}).get("elements", [])
                processed_bundles = []
                
                for bundle in bundles:
                    bundle_info = {
                        "id": bundle.get("id", ""),
                        "name": bundle.get("name", "Unknown"),
                        "version": bundle.get("version", "Unknown"),
                        "description": bundle.get("description", ""),
                        "status": bundle.get("status", ""),
                        "size": bundle.get("size", ""),
                        "productType": bundle.get("productType", ""),
                        "bundleType": bundle.get("bundleType", "")
                    }
                    
                    processed_bundles.append(bundle_info)
                
                result["bundles"] = processed_bundles
                result["bundle_count"] = len(processed_bundles)
            
            return result
            
        except Exception as e:
            _LOGGER.error(f"Error getting VCF bundle details: {e}")
            return {
                "error": str(e),
                "bundles": [],
                "bundle_count": 0
            }

