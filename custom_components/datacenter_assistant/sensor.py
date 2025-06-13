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

def truncate_description(text, max_length=61):
    """Truncate description text to max_length characters + '...' if needed."""
    if not text or not isinstance(text, str):
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

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

        # Create overall status sensors first
        entities.extend([
            VCFOverallStatusSensor(coordinator),
            VCFDomainCountSensor(coordinator),
        ])
        
        # Add entities initially - domain-specific ones will be added via entity registry update
        async_add_entities(entities, True)
        
        # Store coordinator for dynamic entity creation
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
        
        # Store reference to add_entities for dynamic entity creation
        hass.data.setdefault(_DOMAIN, {})["async_add_entities"] = async_add_entities
        
        # Keep track of existing domain entities to avoid duplicates
        existing_domain_entities = set()
        
        async def _coordinator_update_listener():
            """Listen for coordinator updates and create entities for new domains."""
            if coordinator.data and "domain_updates" in coordinator.data:
                new_entities = []
                for domain_id, domain_data in coordinator.data["domain_updates"].items():
                    # Check if we already have entities for this domain
                    if domain_id not in existing_domain_entities:
                        domain_name = domain_data.get("domain_name", "Unknown")
                        domain_prefix = domain_data.get("domain_prefix", f"domain_{domain_id[:8]}_")
                        
                        _LOGGER.info(f"Creating entities for newly discovered domain: {domain_name} with prefix: {domain_prefix}")
                        
                        # Create unique entity IDs using domain prefix as per flow.txt
                        new_entities.extend([
                            VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name, domain_prefix),
                            VCFDomainComponentsSensor(coordinator, domain_id, domain_name, domain_prefix)
                        ])
                        
                        # Mark this domain as having entities
                        existing_domain_entities.add(domain_id)
                
                if new_entities:
                    _LOGGER.info(f"Adding {len(new_entities)} entities for newly discovered domains")
                    async_add_entities(new_entities, True)
        
        def _coordinator_update_callback():
            """Synchronous callback for coordinator updates that schedules entity creation."""
            hass.async_create_task(_coordinator_update_listener())
        
        # Add listener for coordinator updates
        coordinator.async_add_listener(_coordinator_update_callback)
        
        # Schedule domain-specific entity creation after coordinator data is available
        async def _add_domain_entities():
            """Add domain-specific entities after data is available."""
            await coordinator.async_request_refresh()  # Ensure we have fresh data
            
            if coordinator.data and "domain_updates" in coordinator.data:
                new_entities = []
                for domain_id, domain_data in coordinator.data["domain_updates"].items():
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain_{domain_id[:8]}_")
                    
                    _LOGGER.info(f"Creating entities for domain: {domain_name} with prefix: {domain_prefix}")
                    
                    # Create unique entity IDs using domain prefix as per flow.txt
                    new_entities.extend([
                        VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name, domain_prefix),
                        VCFDomainComponentsSensor(coordinator, domain_id, domain_name, domain_prefix)
                    ])
                    
                    # Mark this domain as having entities
                    existing_domain_entities.add(domain_id)
                
                if new_entities:
                    _LOGGER.info(f"Adding {len(new_entities)} domain-specific entities")
                    async_add_entities(new_entities, True)
                else:
                    _LOGGER.warning("No domain-specific entities to create")
            else:
                _LOGGER.warning("No domain update data available for entity creation")
        
        # Delay entity creation slightly to allow coordinator refresh to complete
        hass.loop.call_later(2.0, lambda: hass.async_create_task(_add_domain_entities()))

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
                "total": len(domains),
                "with_updates": sum(1 for d in domain_updates.values() if d.get("update_status") == "updates_available"),
                "up_to_date": sum(1 for d in domain_updates.values() if d.get("update_status") == "up_to_date"),
                "errors": sum(1 for d in domain_updates.values() if d.get("update_status") == "error"),
                "setup_failed": self.coordinator.data.get("setup_failed", False)
            }
            
            # Add domain list
            domain_list = []
            for domain in domains:
                domain_list.append({
                    "domainName": domain.get("name"),
                    "domainID": domain.get("id"),
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
                    "domainName": domain.get("name"),
                    "domainID": domain_id,
                    "status": domain.get("status"),
                    "upd_status": update_info.get("update_status", "unknown"),
                    "curr_ver": update_info.get("current_version"),
                    "sddc_fqdn": domain.get("sddc_manager_fqdn"),
                    "homeassistant_prefix": domain.get("prefix")
                })
            
            return {"domains": domain_details}
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain count attributes: {e}")
            return {"error": str(e)}


class VCFDomainUpdateStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for individual domain update status as per flow.txt requirements."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix=None):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain_{domain_id[:8]}_"
        
        # Use domain prefix for entity naming - simplified without domain name
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix}Status"
        self._attr_unique_id = f"vcf_{self._domain_prefix}{safe_name}_status"

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
                "domain": domain_data.get("domain_name"),
                "prefix": domain_data.get("domain_prefix"),
                "current_version": domain_data.get("current_version"),
                "status": domain_data.get("update_status")
            }
            
            # Add next version information if available
            next_version = domain_data.get("next_version")
            if next_version:
                attributes.update({
                    "next_version": next_version.get("versionNumber"),
                    "next_desc": truncate_description(next_version.get("versionDescription")),
                    "next_date": next_version.get("releaseDate"),
                    "next_vcf_bundle": next_version.get("bundlesToDownload", [])
                })
            
            # Add error if present
            if "error" in domain_data:
                attributes["error"] = domain_data["error"]
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain {self._domain_name} attributes: {e}")
            return {"error": str(e)}


class VCFDomainComponentsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for individual domain components with available updates."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix=None):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain_{domain_id[:8]}_"
        
        # Use domain prefix for entity naming - simplified name since prefix already indicates domain
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix}Available Updates"
        self._attr_unique_id = f"vcf_{self._domain_prefix}{safe_name}_available_updates"
        self._attr_icon = "mdi:update"

    @property
    def state(self):
        """Return count of components with available updates."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            component_updates = domain_data.get("component_updates", {})
            return len(component_updates)
        except Exception:
            return 0

    @property
    def extra_state_attributes(self):
        """Return component update details for this domain."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            component_updates = domain_data.get("component_updates", {})
            
            # Sort components to put SDDC Manager first, then others alphabetically
            sorted_components = {}
            
            # Add SDDC Manager first if it exists
            sddc_components = {k: v for k, v in component_updates.items() if 'sddc' in k.lower() or 'manager' in k.lower()}
            for comp_name, comp_data in sddc_components.items():
                sorted_components[comp_name] = {
                    "desc": truncate_description(comp_data.get("description")),
                    "ver": comp_data.get("version"),
                    "bundle_id": comp_data.get("id")
                }
            
            # Add other components alphabetically
            other_components = {k: v for k, v in component_updates.items() if k not in sddc_components}
            for comp_name in sorted(other_components.keys()):
                comp_data = other_components[comp_name]
                sorted_components[comp_name] = {
                    "desc": truncate_description(comp_data.get("description")),
                    "ver": comp_data.get("version"),
                    "bundle_id": comp_data.get("id")
                }
            
            return {
                "domain": domain_data.get("domain_name"),
                "updates_available": len(component_updates),
                "components": sorted_components
            }
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain {self._domain_name} available updates: {e}")
            return {"error": str(e)}

