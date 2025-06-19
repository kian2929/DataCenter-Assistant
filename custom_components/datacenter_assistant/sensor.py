import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
from aiohttp import ClientError
import asyncio
from .coordinator import get_coordinator, get_resource_coordinator
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

        # Get the resource coordinator that was created in get_coordinator
        resource_coordinator = hass.data.get(_DOMAIN, {}).get("resource_coordinator")
        if resource_coordinator:
            try:
                await resource_coordinator.async_config_entry_first_refresh()
                _LOGGER.info("VCF resource coordinator started successfully")
            except Exception as e:
                _LOGGER.warning("VCF resource coordinator first refresh failed: %s", e)
        else:
            _LOGGER.error("Resource coordinator not found - this may cause issues with resource monitoring")

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
        existing_resource_entities = set()
        
        async def _resource_update_listener():
            """Listen for resource coordinator updates and create resource entities."""
            if resource_coordinator and resource_coordinator.data and "domain_resources" in resource_coordinator.data:
                new_entities = []
                domain_resources = resource_coordinator.data.get("domain_resources", {})
                
                for domain_id, domain_data in domain_resources.items():
                    domain_key = f"{domain_id}_resources"
                    if domain_key in existing_resource_entities:
                        continue
                        
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_resource_entities) + 1}")
                    
                    _LOGGER.info(f"Creating resource entities for domain: {domain_name} with prefix: {domain_prefix}")
                    
                    # Create domain capacity sensors
                    for resource_type in ["cpu", "memory", "storage"]:
                        new_entities.append(
                            VCFDomainCapacitySensor(resource_coordinator, domain_id, domain_name, domain_prefix, resource_type)
                        )
                    
                    # Create cluster host count sensors
                    clusters = domain_data.get("clusters", [])
                    for cluster in clusters:
                        cluster_id = cluster.get("id")
                        cluster_name = cluster.get("name", "Unknown")
                        new_entities.append(
                            VCFClusterHostCountSensor(resource_coordinator, domain_id, domain_name, domain_prefix, cluster_id, cluster_name)
                        )
                        
                        # Create host resource sensors
                        hosts = cluster.get("hosts", [])
                        for host in hosts:
                            host_id = host.get("id")
                            hostname = host.get("hostname", "Unknown")
                            for resource_type in ["cpu", "memory", "storage"]:
                                new_entities.append(
                                    VCFHostResourceSensor(resource_coordinator, domain_id, domain_name, domain_prefix, host_id, hostname, resource_type)
                                )
                    
                    existing_resource_entities.add(domain_key)
                
                if new_entities:
                    _LOGGER.info(f"Adding {len(new_entities)} resource entities")
                    async_add_entities(new_entities, True)
        
        async def _coordinator_update_listener():
            """Listen for coordinator updates and create entities for new domains."""
            if coordinator.data and "domain_updates" in coordinator.data:
                new_entities = []
                for domain_id, domain_data in coordinator.data["domain_updates"].items():
                    # Check if we already have entities for this domain
                    if domain_id not in existing_domain_entities:
                        domain_name = domain_data.get("domain_name", "Unknown")
                        domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_domain_entities) + 1}")
                        
                        _LOGGER.info(f"Creating entities for newly discovered domain: {domain_name} with prefix: {domain_prefix}")
                        
                        # Create unique entity IDs using domain prefix
                        new_entities.extend([
                            VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name, domain_prefix)
                        ])
                        
                        # Mark this domain as having entities
                        existing_domain_entities.add(domain_id)
                
                if new_entities:
                    _LOGGER.info(f"Adding {len(new_entities)} entities for newly discovered domains")
                    async_add_entities(new_entities, True)

        async def _resource_coordinator_update_listener():
            """Listen for resource coordinator updates and create entities for new resources."""
            if resource_coordinator and resource_coordinator.data and "domain_resources" in resource_coordinator.data:
                new_entities = []
                domain_resources = resource_coordinator.data["domain_resources"]
                
                for domain_id, domain_data in domain_resources.items():
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_resource_entities) + 1}")
                    
                    # Create domain capacity sensors
                    domain_key = f"{domain_id}_capacity"
                    if domain_key not in existing_resource_entities:
                        capacity = domain_data.get("capacity", {})
                        if capacity:
                            # Create capacity sensors for CPU, Memory, Storage
                            new_entities.extend([
                                VCFDomainCapacitySensor(resource_coordinator, domain_id, domain_name, domain_prefix, "cpu"),
                                VCFDomainCapacitySensor(resource_coordinator, domain_id, domain_name, domain_prefix, "memory"),
                                VCFDomainCapacitySensor(resource_coordinator, domain_id, domain_name, domain_prefix, "storage")
                            ])
                        existing_resource_entities.add(domain_key)
                    
                    # Create cluster host count sensors
                    clusters = domain_data.get("clusters", [])
                    for cluster in clusters:
                        cluster_id = cluster.get("id")
                        cluster_name = cluster.get("name", "Unknown")
                        cluster_key = f"{domain_id}_{cluster_id}_hostcount"
                        
                        if cluster_key not in existing_resource_entities:
                            new_entities.append(
                                VCFClusterHostCountSensor(resource_coordinator, domain_id, domain_name, domain_prefix, cluster_id, cluster_name)
                            )
                            existing_resource_entities.add(cluster_key)
                        
                        # Create host resource sensors
                        hosts = cluster.get("hosts", [])
                        for host in hosts:
                            host_id = host.get("id")
                            hostname = host.get("hostname", "Unknown")
                            
                            # Create sensors for CPU, Memory, Storage for each host
                            for resource_type in ["cpu", "memory", "storage"]:
                                host_key = f"{domain_id}_{host_id}_{resource_type}"
                                if host_key not in existing_resource_entities:
                                    new_entities.append(
                                        VCFHostResourceSensor(resource_coordinator, domain_id, domain_name, domain_prefix, 
                                                             host_id, hostname, resource_type)
                                    )
                                    existing_resource_entities.add(host_key)
                
                if new_entities:
                    _LOGGER.info(f"Adding {len(new_entities)} resource entities")
                    async_add_entities(new_entities, True)
        
        def _coordinator_update_callback():
            """Synchronous callback for coordinator updates that schedules entity creation."""
            hass.async_create_task(_coordinator_update_listener())
        
        def _resource_coordinator_update_callback():
            """Synchronous callback for resource coordinator updates that schedules entity creation."""
            hass.async_create_task(_resource_update_listener())
        
        # Add listener for coordinator updates
        coordinator.async_add_listener(_coordinator_update_callback)
        
        # Add listener for resource coordinator updates
        if resource_coordinator:
            resource_coordinator.async_add_listener(_resource_coordinator_update_callback)
        
        # Schedule domain-specific entity creation after coordinator data is available
        async def _add_domain_entities():
            """Add domain-specific entities after data is available."""
            await coordinator.async_request_refresh()  # Ensure we have fresh data
            
            if coordinator.data and "domain_updates" in coordinator.data:
                new_entities = []
                for i, (domain_id, domain_data) in enumerate(coordinator.data["domain_updates"].items()):
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{i + 1}")
                    
                    _LOGGER.info(f"Creating entities for domain: {domain_name} with prefix: {domain_prefix}")
                    
                    # Create unique entity IDs using domain prefix
                    new_entities.extend([
                        VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name, domain_prefix)
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

        async def _add_resource_entities():
            """Add resource-specific entities after data is available."""
            if resource_coordinator:
                await resource_coordinator.async_request_refresh()  # Ensure we have fresh data
                await _resource_update_listener()
        
        # Delay entity creation slightly to allow coordinator refresh to complete
        hass.loop.call_later(2.0, lambda: hass.async_create_task(_add_domain_entities()))
        hass.loop.call_later(3.0, lambda: hass.async_create_task(_add_resource_entities()))

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
    """Sensor for individual domain update status requirements."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix=None):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain{domain_id[:8]}"
        
        # Use domain prefix for entity naming - simplified without domain name
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} Status"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_name}_status"

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
        """Return domain-specific update attributes format."""
        try:
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            
            # Only show essential attributes in frontend
            attributes = {
                "domain": domain_data.get("domain_name"),
                "homeassistant_prefix": domain_data.get("domain_prefix"),
                "current_version": domain_data.get("current_version")
            }
            
            # Add next release information if available
            next_release = domain_data.get("next_release")
            if next_release:
                attributes.update({
                    "next_version": next_release.get("version"),
                    "release_date": next_release.get("releaseDate")
                })
            
            # Add error if present (important for troubleshooting)
            if "error" in domain_data:
                attributes["error"] = domain_data["error"]
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting domain {self._domain_name} attributes: {e}")
            return {"error": str(e)}


class VCFDomainCapacitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for domain capacity (CPU, Memory, Storage)."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, resource_type):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix
        self._resource_type = resource_type
        
        # Create entity name and unique ID
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} {resource_type.upper()}"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_name}_{resource_type}"

    @property
    def icon(self):
        if self._resource_type == "cpu":
            return "mdi:cpu-64-bit"
        elif self._resource_type == "memory":
            return "mdi:memory"
        elif self._resource_type == "storage":
            return "mdi:harddisk"
        else:
            return "mdi:server"

    @property
    def state(self):
        """Return the usage percentage for this resource."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            capacity = domain_data.get("capacity", {})
            resource_info = capacity.get(self._resource_type, {})
            
            if self._resource_type == "cpu":
                used = resource_info.get("used", {}).get("value", 0)
                total = resource_info.get("total", {}).get("value", 0)
            elif self._resource_type == "memory":
                used = resource_info.get("used", {}).get("value", 0)
                total = resource_info.get("total", {}).get("value", 0)
            elif self._resource_type == "storage":
                used = resource_info.get("used", {}).get("value", 0)
                total = resource_info.get("total", {}).get("value", 0)
            else:
                return 0
            
            if total > 0:
                return round((used / total) * 100, 2)
            return 0
            
        except Exception as e:
            _LOGGER.error(f"Error getting capacity for {self._domain_name} {self._resource_type}: {e}")
            return 0

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            capacity = domain_data.get("capacity", {})
            resource_info = capacity.get(self._resource_type, {})
            
            attributes = {
                "domain": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "resource_type": self._resource_type
            }
            
            if self._resource_type == "cpu":
                used = resource_info.get("used", {})
                total = resource_info.get("total", {})
                attributes.update({
                    "used_value": used.get("value", 0),
                    "used_unit": used.get("unit", "GHz"),
                    "total_value": total.get("value", 0),
                    "total_unit": total.get("unit", "GHz"),
                    "number_of_cores": resource_info.get("numberOfCores", 0)
                })
            elif self._resource_type in ["memory", "storage"]:
                used = resource_info.get("used", {})
                total = resource_info.get("total", {})
                attributes.update({
                    "used_value": used.get("value", 0),
                    "used_unit": used.get("unit", "GB"),
                    "total_value": total.get("value", 0),
                    "total_unit": total.get("unit", "GB")
                })
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting capacity attributes for {self._domain_name} {self._resource_type}: {e}")
            return {"error": str(e)}


class VCFClusterHostCountSensor(CoordinatorEntity, SensorEntity):
    """Sensor for cluster host count."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, cluster_id, cluster_name):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix
        self._cluster_id = cluster_id
        self._cluster_name = cluster_name
        
        # Create entity name and unique ID
        safe_domain_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        safe_cluster_name = cluster_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} {cluster_name} host count"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_domain_name}_{safe_cluster_name}_host_count"
        self._attr_icon = "mdi:server-network"

    @property
    def state(self):
        """Return the host count for this cluster."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            clusters = domain_data.get("clusters", [])
            
            for cluster in clusters:
                if cluster.get("id") == self._cluster_id:
                    return cluster.get("host_count", 0)
            
            return 0
            
        except Exception as e:
            _LOGGER.error(f"Error getting host count for cluster {self._cluster_name}: {e}")
            return 0

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            clusters = domain_data.get("clusters", [])
            
            attributes = {
                "domain": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "cluster_name": self._cluster_name,
                "cluster_id": self._cluster_id
            }
            
            for cluster in clusters:
                if cluster.get("id") == self._cluster_id:
                    hosts = cluster.get("hosts", [])
                    host_list = []
                    for host in hosts:
                        host_list.append({
                            "hostname": host.get("hostname", "Unknown"),
                            "fqdn": host.get("fqdn", "Unknown"),
                            "id": host.get("id", "Unknown")
                        })
                    attributes["hosts"] = host_list
                    break
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting cluster attributes for {self._cluster_name}: {e}")
            return {"error": str(e)}


class VCFHostResourceSensor(CoordinatorEntity, SensorEntity):
    """Sensor for host resource usage (CPU, Memory, Storage)."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, host_id, hostname, resource_type):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix
        self._host_id = host_id
        self._hostname = hostname
        self._resource_type = resource_type
        
        # Create entity name and unique ID
        safe_domain_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        safe_hostname = hostname.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} {hostname} {resource_type.upper()}"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_domain_name}_{safe_hostname}_{resource_type}"

    @property
    def icon(self):
        if self._resource_type == "cpu":
            return "mdi:cpu-64-bit"
        elif self._resource_type == "memory":
            return "mdi:memory"
        elif self._resource_type == "storage":
            return "mdi:harddisk"
        else:
            return "mdi:server"

    @property
    def state(self):
        """Return the usage percentage for this host resource."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            clusters = domain_data.get("clusters", [])
            
            # Find the host in the clusters
            for cluster in clusters:
                hosts = cluster.get("hosts", [])
                for host in hosts:
                    if host.get("id") == self._host_id:
                        resource_info = host.get(self._resource_type, {})
                        
                        if self._resource_type == "cpu":
                            used = resource_info.get("used_mhz", 0)
                            total = resource_info.get("total_mhz", 0)
                        elif self._resource_type in ["memory", "storage"]:
                            used = resource_info.get("used_mb", 0)
                            total = resource_info.get("total_mb", 0)
                        else:
                            return 0
                        
                        if total > 0:
                            return round((used / total) * 100, 2)
                        return 0
            
            return 0
            
        except Exception as e:
            _LOGGER.error(f"Error getting {self._resource_type} usage for host {self._hostname}: {e}")
            return 0

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            domain_resources = self.coordinator.data.get("domain_resources", {})
            domain_data = domain_resources.get(self._domain_id, {})
            clusters = domain_data.get("clusters", [])
            
            attributes = {
                "domain": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "hostname": self._hostname,
                "host_id": self._host_id,
                "resource_type": self._resource_type
            }
            
            # Find the host in the clusters
            for cluster in clusters:
                hosts = cluster.get("hosts", [])
                for host in hosts:
                    if host.get("id") == self._host_id:
                        resource_info = host.get(self._resource_type, {})
                        attributes["fqdn"] = host.get("fqdn", "Unknown")
                        
                        if self._resource_type == "cpu":
                            attributes.update({
                                "used_mhz": resource_info.get("used_mhz", 0),
                                "total_mhz": resource_info.get("total_mhz", 0),
                                "cores": resource_info.get("cores", 0)
                            })
                        elif self._resource_type in ["memory", "storage"]:
                            used_mb = resource_info.get("used_mb", 0)
                            total_mb = resource_info.get("total_mb", 0)
                            attributes.update({
                                "used_mb": used_mb,
                                "total_mb": total_mb,
                                "used_gb": round(used_mb / 1024, 2) if used_mb > 0 else 0,
                                "total_gb": round(total_mb / 1024, 2) if total_mb > 0 else 0
                            })
                        break
                if attributes.get("fqdn"):  # If we found the host, break outer loop too
                    break
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting {self._resource_type} attributes for host {self._hostname}: {e}")
            return {"error": str(e)}

