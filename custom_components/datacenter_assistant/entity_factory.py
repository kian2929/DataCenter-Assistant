"""Entity factory for creating VCF sensors."""
import logging
from .base_sensors import VCFDomainBaseSensor, VCFResourceBaseSensor, VCFHostResourceBaseSensor
from .utils import safe_name_conversion

_LOGGER = logging.getLogger(__name__)


class VCFEntityFactory:
    """Factory class to create VCF sensor entities."""
    
    @staticmethod
    def create_domain_sensors(coordinator, domain_id, domain_name, domain_prefix):
        """Create all sensors for a domain."""
        return [
            VCFDomainUpdateStatusSensor(coordinator, domain_id, domain_name, domain_prefix),
            VCFDomainUpgradeStatusSensor(coordinator, domain_id, domain_name, domain_prefix),
            VCFDomainUpgradeLogsSensor(coordinator, domain_id, domain_name, domain_prefix)
        ]
    
    @staticmethod
    def create_resource_sensors(resource_coordinator, domain_id, domain_name, domain_prefix, domain_data):
        """Create all resource sensors for a domain."""
        entities = []
        
        # Create domain capacity sensors
        capacity = domain_data.get("capacity", {})
        if capacity:
            for resource_type in ["cpu", "memory", "storage"]:
                entities.append(
                    VCFDomainCapacitySensor(resource_coordinator, domain_id, domain_name, domain_prefix, resource_type)
                )
        
        # Create cluster and host sensors
        clusters = domain_data.get("clusters", [])
        for cluster in clusters:
            cluster_id = cluster.get("id")
            cluster_name = cluster.get("name", "Unknown")
            
            # Create cluster host count sensor
            entities.append(
                VCFClusterHostCountSensor(resource_coordinator, domain_id, domain_name, domain_prefix, cluster_id, cluster_name)
            )
            
            # Create host resource sensors
            hosts = cluster.get("hosts", [])
            for host in hosts:
                host_id = host.get("id")
                hostname = host.get("hostname", "Unknown")
                
                for resource_type in ["cpu", "memory", "storage"]:
                    entities.append(
                        VCFHostResourceSensor(resource_coordinator, domain_id, domain_name, domain_prefix, host_id, hostname, resource_type)
                    )
        
        return entities


class VCFDomainUpdateStatusSensor(VCFDomainBaseSensor):
    """Sensor for individual domain update status."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix):
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, "Status")
    
    @property
    def state(self):
        """Return the update status of this domain."""
        domain_data = self.get_domain_data()
        if not domain_data:
            return "unknown"
        return domain_data.get("update_status", "unknown")
    
    @property
    def icon(self):
        state = self.state
        if state == "updates_available":
            return "mdi:update"
        elif state == "up_to_date":
            return "mdi:check-circle"
        elif state == "error":
            return "mdi:alert-circle"
        else:
            return "mdi:sync-alert"
    
    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            domain_data = self.get_domain_data()
            if not domain_data:
                return {"error": "No domain data"}
            
            attributes = {
                "domain_name": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "current_version": domain_data.get("current_version"),
                "update_status": domain_data.get("update_status", "unknown")
            }
            
            next_release = domain_data.get("next_release")
            if next_release:
                attributes.update({
                    "next_version": next_release.get("version"),
                    "next_release_date": next_release.get("releaseDate"),
                    "next_description": next_release.get("description", ""),
                    "next_downloadUrl": next_release.get("downloadUrl", ""),
                    "next_bundleId": next_release.get("bundleId", "")
                })
            
            return attributes
        except Exception as e:
            _LOGGER.error(f"Error getting domain update attributes for {self._domain_name}: {e}")
            return {"error": str(e)}


class VCFDomainCapacitySensor(VCFResourceBaseSensor):
    """Sensor for domain capacity (CPU, Memory, Storage)."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, resource_type):
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, resource_type)
    
    @property
    def state(self):
        """Return the usage percentage for this domain resource."""
        try:
            domain_data = self.get_resource_data()
            if not domain_data:
                return 0
            
            capacity = domain_data.get("capacity", {})
            resource_info = capacity.get(self._resource_type, {})
            
            if not resource_info:
                return 0
            
            if self._resource_type == "cpu":
                used = resource_info.get("used", {})
                total = resource_info.get("total", {})
                used_value = used.get("value", 0)
                total_value = total.get("value", 1)
                return round((used_value / total_value) * 100, 1) if total_value > 0 else 0
            
            elif self._resource_type in ["memory", "storage"]:
                used = resource_info.get("used", {})
                total = resource_info.get("total", {})
                used_value = used.get("value", 0)
                total_value = total.get("value", 1)
                return round((used_value / total_value) * 100, 1) if total_value > 0 else 0
            
            return 0
        except Exception as e:
            _LOGGER.error(f"Error getting {self._resource_type} state for domain {self._domain_name}: {e}")
            return 0
    
    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            domain_data = self.get_resource_data()
            if not domain_data:
                return {"error": "No domain data"}
            
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


class VCFClusterHostCountSensor(VCFDomainBaseSensor):
    """Sensor for cluster host count."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, cluster_id, cluster_name):
        self._cluster_id = cluster_id
        self._cluster_name = cluster_name
        
        # Override the naming pattern for cluster sensors
        safe_domain_name = safe_name_conversion(domain_name)
        safe_cluster_name = safe_name_conversion(cluster_name)
        
        name = f"VCF {domain_prefix} {cluster_name} host count"
        unique_id = f"vcf_{domain_prefix}_{safe_domain_name}_{safe_cluster_name}_host_count"
        
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, "", "mdi:server-network")
        
        # Override the generated name and unique_id
        self._attr_name = name
        self._attr_unique_id = unique_id
    
    @property
    def state(self):
        """Return the host count for this cluster."""
        try:
            domain_data = self.safe_get_data("domain_resources", self._domain_id, default={})
            if not domain_data:
                return 0
            
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
        """Return cluster details."""
        try:
            domain_data = self.safe_get_data("domain_resources", self._domain_id, default={})
            if not domain_data:
                return {"error": "No domain data"}
            
            clusters = domain_data.get("clusters", [])
            for cluster in clusters:
                if cluster.get("id") == self._cluster_id:
                    hosts = cluster.get("hosts", [])
                    host_details = []
                    
                    for host in hosts:
                        host_details.append({
                            "hostname": host.get("hostname", "Unknown"),
                            "fqdn": host.get("fqdn", "Unknown"),
                            "host_id": host.get("id")
                        })
                    
                    return {
                        "domain": self._domain_name,
                        "domain_prefix": self._domain_prefix,
                        "cluster_name": self._cluster_name,
                        "cluster_id": self._cluster_id,
                        "hosts": host_details
                    }
            
            return {"error": "Cluster not found"}
        except Exception as e:
            _LOGGER.error(f"Error getting cluster attributes for {self._cluster_name}: {e}")
            return {"error": str(e)}


class VCFHostResourceSensor(VCFHostResourceBaseSensor):
    """Sensor for host resource usage (CPU, Memory, Storage)."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, host_id, hostname, resource_type):
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, host_id, hostname, resource_type)


class VCFDomainUpgradeStatusSensor(VCFDomainBaseSensor):
    """Sensor for individual domain upgrade status."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix):
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, "Upgrade Status")
        
        # Listen for upgrade status change events
        self._remove_listener = None
        
    async def async_added_to_hass(self):
        """Run when sensor is added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Listen for VCF upgrade status change events
        self._remove_listener = self.hass.bus.async_listen(
            "vcf_upgrade_status_changed",
            self._handle_upgrade_status_change
        )
    
    async def async_will_remove_from_hass(self):
        """Run when sensor is removed from Home Assistant."""
        if self._remove_listener:
            self._remove_listener()
    
    def _handle_upgrade_status_change(self, event):
        """Handle upgrade status change events."""
        if event.data.get("domain_id") == self._domain_id:
            # Schedule update on the Home Assistant event loop (thread-safe)
            self.hass.loop.call_soon_threadsafe(
                lambda: self.hass.async_create_task(self._async_update_state())
            )
    
    async def _async_update_state(self):
        """Async method to update entity state."""
        self.async_schedule_update_ha_state()
    
    @property
    def state(self):
        """Return the upgrade status of this domain."""
        try:
            # Get upgrade service from hass data
            upgrade_service = self.hass.data.get("datacenter_assistant", {}).get("upgrade_service")
            if upgrade_service:
                return upgrade_service.get_upgrade_status(self._domain_id)
            return "waiting_for_initiation"
        except Exception as e:
            _LOGGER.error(f"Error getting upgrade status for domain {self._domain_name}: {e}")
            return "waiting_for_initiation"
    
    @property
    def icon(self):
        state = self.state
        icons = {
            "waiting_for_initiation": "mdi:clock-outline",
            "targeting_new_vcf_version": "mdi:target",
            "downloading_bundles": "mdi:download",
            "running_prechecks": "mdi:check-circle-outline",
            "waiting_acknowledgement": "mdi:alert-circle-check",
            "starting_upgrades": "mdi:rocket-launch-outline",
            "upgrading_sddcmanager": "mdi:server-network",
            "upgrading_nsx": "mdi:network",
            "upgrading_vcenter": "mdi:server",
            "upgrading_esx_cluster": "mdi:server-network",
            "final_validation": "mdi:check-decagram",
            "successfully_completed": "mdi:check-circle",
            "failed": "mdi:alert-circle"
        }
        return icons.get(state, "mdi:sync-alert")
    
    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            attributes = {
                "domain_name": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "upgrade_status": self.state
            }
            
            # Add domain update information for context
            domain_data = self.get_domain_data()
            if domain_data:
                attributes.update({
                    "current_version": domain_data.get("current_version"),
                    "update_available": domain_data.get("update_status") == "updates_available"
                })
                
                next_release = domain_data.get("next_release")
                if next_release:
                    attributes["target_version"] = next_release.get("version")
            
            return attributes
        except Exception as e:
            _LOGGER.error(f"Error getting upgrade status attributes for {self._domain_name}: {e}")
            return {"error": str(e)}


class VCFDomainUpgradeLogsSensor(VCFDomainBaseSensor):
    """Sensor for individual domain upgrade logs."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix):
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, "Upgrade Logs")
        
        # Listen for upgrade logs change events
        self._remove_listener = None
        
    async def async_added_to_hass(self):
        """Run when sensor is added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Listen for VCF upgrade logs change events
        self._remove_listener = self.hass.bus.async_listen(
            "vcf_upgrade_logs_changed",
            self._handle_upgrade_logs_change
        )
    
    async def async_will_remove_from_hass(self):
        """Run when sensor is removed from Home Assistant."""
        if self._remove_listener:
            self._remove_listener()
    
    def _handle_upgrade_logs_change(self, event):
        """Handle upgrade logs change events."""
        if event.data.get("domain_id") == self._domain_id:
            # Schedule update on the Home Assistant event loop (thread-safe)
            self.hass.loop.call_soon_threadsafe(
                lambda: self.hass.async_create_task(self._async_update_logs_state())
            )
    
    async def _async_update_logs_state(self):
        """Async method to update entity state."""
        self.async_schedule_update_ha_state()
    
    @property
    def state(self):
        """Return the upgrade logs of this domain."""
        try:
            # Get upgrade service from hass data
            upgrade_service = self.hass.data.get("datacenter_assistant", {}).get("upgrade_service")
            if upgrade_service:
                logs = upgrade_service.get_upgrade_logs(self._domain_id)
                # Return first 255 characters for state (Home Assistant limitation)
                return logs[:255] if len(logs) > 255 else logs
            return "No Messages"
        except Exception as e:
            _LOGGER.error(f"Error getting upgrade logs for domain {self._domain_name}: {e}")
            return "No Messages"
    
    @property
    def icon(self):
        return "mdi:text-box-multiple"
    
    @property
    def extra_state_attributes(self):
        """Return full logs in attributes."""
        try:
            attributes = {
                "domain_name": self._domain_name,
                "domain_prefix": self._domain_prefix
            }
            
            # Get full logs for markdown display
            upgrade_service = self.hass.data.get("datacenter_assistant", {}).get("upgrade_service")
            if upgrade_service:
                full_logs = upgrade_service.get_upgrade_logs(self._domain_id)
                attributes["full_logs"] = full_logs
                attributes["markdown"] = full_logs  # For dashboard card display
            else:
                attributes["full_logs"] = "No Messages"
                attributes["markdown"] = "No Messages"
            
            return attributes
        except Exception as e:
            _LOGGER.error(f"Error getting upgrade logs attributes for {self._domain_name}: {e}")
            return {"error": str(e)}
