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

        # Create overall status sensors
        entities.extend([
            VCFOverallStatusSensor(coordinator),
            VCFDomainCountSensor(coordinator),
        ])
        
        # Create domain-specific sensors based on discovered domains
        if coordinator.data and "domain_updates" in coordinator.data:
            for domain_id, domain_data in coordinator.data["domain_updates"].items():
                domain_name = domain_data.get("domain_name", "Unknown")
                entities.extend([
                    VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name),
                    VCFDomainComponentsSensor(coordinator, domain_id, domain_name)
                ])

        # Store coordinator for other components
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator

    except Exception as e:
        _LOGGER.error("VCF sensors could not be initialized: %s", e)
        # Create empty entities list if VCF setup fails
        entities = []

    async_add_entities(entities, True)


class VCFOverallStatusSensor(CoordinatorEntity, SensorEntity):
    """Overall VCF system status sensor."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Overall Status"
        self._attr_unique_id = "vcf_overall_status"

    @property
    def icon(self):
        if self.state == "updates_available":
            return "mdi:update"
        elif self.state == "up_to_date":
            return "mdi:check-circle"
        elif self.state == "setup_failed":
            return "mdi:alert-circle"
        else:
            return "mdi:sync-alert"

    @property
    def state(self):
        """Return the overall state of VCF system."""
        try:
            if self.coordinator.data is None:
                return "not_connected"
                
            # Check if setup failed (no active domains)
            if self.coordinator.data.get("setup_failed"):
                return "setup_failed"
                
            domain_updates = self.coordinator.data.get("domain_updates", {})
            if not domain_updates:
                return "no_domains"
            
            # Check if any domain has updates available
            has_updates = False
            has_errors = False
            
            for domain_data in domain_updates.values():
                status = domain_data.get("update_status", "unknown")
                if status == "updates_available":
                    has_updates = True
                elif status == "error":
                    has_errors = True
            
            if has_updates:
                return "updates_available"
            elif has_errors:
                return "partial_error"
            else:
                return "up_to_date"
                
        except Exception as e:
            _LOGGER.error(f"Error checking VCF overall status: {e}")
            return "error"

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            if not self.coordinator.data:
                return {"error": "No data available"}
                
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domains = self.coordinator.data.get("domains", [])
            
            attributes = {
                "total_domains": len(domains),
                "domains_with_updates": sum(1 for d in domain_updates.values() if d.get("update_status") == "updates_available"),
                "domains_up_to_date": sum(1 for d in domain_updates.values() if d.get("update_status") == "up_to_date"),
                "domains_with_errors": sum(1 for d in domain_updates.values() if d.get("update_status") == "error"),
                "last_check": self.coordinator.last_update_success,
                "setup_failed": self.coordinator.data.get("setup_failed", False)
            }
            
            # Add domain list
            domain_list = []
            for domain in domains:
                domain_list.append({
                    "name": domain.get("name"),
                    "id": domain.get("id"),
                    "status": domain_updates.get(domain.get("id"), {}).get("update_status", "unknown")
                })
            attributes["domains"] = domain_list
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting VCF overall attributes: {e}")
            return {"error": str(e)}


class VCFDomainCountSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing count of active domains."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Active Domains Count"
        self._attr_unique_id = "vcf_active_domains_count"
        self._attr_icon = "mdi:server-network"

    @property
    def state(self):
        """Return the count of active domains."""
        try:
            domains = self.coordinator.data.get("domains", [])
            return len(domains)
        except Exception:
            return 0

    @property
    def extra_state_attributes(self):
        """Return domain details."""
        try:
            domains = self.coordinator.data.get("domains", [])
            domain_updates = self.coordinator.data.get("domain_updates", {})
            
            domain_details = []
            for domain in domains:
                domain_id = domain.get("id")
                update_info = domain_updates.get(domain_id, {})
                
                domain_details.append({
                    "name": domain.get("name"),
                    "id": domain_id,
                    "status": domain.get("status"),
                    "update_status": update_info.get("update_status", "unknown"),
                    "current_version": update_info.get("current_version"),
                    "sddc_manager_fqdn": domain.get("sddc_manager_fqdn"),
                    "prefix": domain.get("prefix")
                })
            
            return {"domains": domain_details}
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain count attributes: {e}")
            return {"error": str(e)}


class VCFDomainUpdateStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for individual domain update status as per flow.txt requirements."""
    
    def __init__(self, coordinator, domain_id, domain_name):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._attr_name = f"VCF {domain_name} Updates"
        self._attr_unique_id = f"vcf_{domain_name.lower().replace(' ', '_')}_updates"

    @property
    def icon(self):
        if self.state == "updates_available":
            return "mdi:update"
        elif self.state == "up_to_date":
            return "mdi:check-circle"
        else:
            return "mdi:sync-alert"

    @property
    def state(self):
        """Return update status for this domain."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            return domain_data.get("update_status", "unknown")
        except Exception:
            return "error"

    @property
    def extra_state_attributes(self):
        """Return domain-specific update attributes as per flow.txt format."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            
            attributes = {
                "domain_name": domain_data.get("domain_name"),
                "domain_prefix": domain_data.get("domain_prefix"),
                "current_version": domain_data.get("current_version"),
                "update_status": domain_data.get("update_status")
            }
            
            # Add next version information if available (following flow.txt naming)
            next_version = domain_data.get("next_version")
            if next_version:
                attributes.update({
                    "nextVersion_versionNumber": next_version.get("versionNumber"),
                    "nextVersion_versionDescription": next_version.get("versionDescription"),
                    "nextVersion_releaseDate": next_version.get("releaseDate"),
                    "nextVersion_bundlesToDownload": next_version.get("bundlesToDownload", [])
                })
            
            # Add component updates (following flow.txt format)
            component_updates = domain_data.get("component_updates", {})
            for comp_name, comp_data in component_updates.items():
                attributes[f"nextVersion_componentUpdates_{comp_name}_description"] = comp_data.get("description")
                attributes[f"nextVersion_componentUpdates_{comp_name}_version"] = comp_data.get("version")
                attributes[f"nextVersion_componentUpdates_{comp_name}_id"] = comp_data.get("id")
            
            # Add error if present
            if "error" in domain_data:
                attributes["error"] = domain_data["error"]
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain {self._domain_name} attributes: {e}")
            return {"error": str(e)}


class VCFDomainComponentsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for individual domain components that can be updated."""
    
    def __init__(self, coordinator, domain_id, domain_name):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._attr_name = f"VCF {domain_name} Components"
        self._attr_unique_id = f"vcf_{domain_name.lower().replace(' ', '_')}_components"
        self._attr_icon = "mdi:package-variant"

    @property
    def state(self):
        """Return count of components with updates available."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            component_updates = domain_data.get("component_updates", {})
            return len(component_updates)
        except Exception:
            return 0

    @property
    def extra_state_attributes(self):
        """Return component details for this domain."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            component_updates = domain_data.get("component_updates", {})
            
            # Format components for easy consumption
            components = {}
            for comp_name, comp_data in component_updates.items():
                components[comp_name] = {
                    "description": comp_data.get("description"),
                    "version": comp_data.get("version"),
                    "bundle_id": comp_data.get("id"),
                    "component_type": comp_data.get("componentType")
                }
            
            return {
                "domain_name": domain_data.get("domain_name"),
                "component_count": len(component_updates),
                "components": components
            }
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain {self._domain_name} components: {e}")
            return {"error": str(e)}

