"""Base sensor classes for VCF sensors."""
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .utils import safe_name_conversion, get_resource_icon

_LOGGER = logging.getLogger(__name__)


class VCFBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for all VCF sensors."""
    
    def __init__(self, coordinator, name, unique_id, icon="mdi:server"):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = icon
    
    def safe_get_data(self, *keys, default=None):
        """Safely get nested data from coordinator."""
        try:
            data = self.coordinator.data
            for key in keys:
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    _LOGGER.debug(f"Key '{key}' not found in coordinator data for {self._attr_name}")
                    return default
            return data
        except Exception as e:
            _LOGGER.warning(f"Error accessing coordinator data for {self._attr_name}: {e}")
            return default


class VCFDomainBaseSensor(VCFBaseSensor):
    """Base class for domain-specific sensors."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, 
                 sensor_type, icon="mdi:server"):
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix
        
        safe_name = safe_name_conversion(domain_name)
        name = f"VCF {domain_prefix} {sensor_type}"
        unique_id = f"vcf_{domain_prefix}_{safe_name}_{sensor_type.lower().replace(' ', '_')}"
        
        super().__init__(coordinator, name, unique_id, icon)
    
    def get_domain_data(self, data_key="domain_updates"):
        """Get data for this specific domain."""
        return self.safe_get_data(data_key, self._domain_id, default={})


class VCFResourceBaseSensor(VCFBaseSensor):
    """Base class for resource-specific sensors."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, 
                 resource_type, entity_suffix=""):
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix
        self._resource_type = resource_type
        
        safe_name = safe_name_conversion(domain_name)
        name = f"VCF {domain_prefix} {resource_type.upper()}{entity_suffix}"
        unique_id = f"vcf_{domain_prefix}_{safe_name}_{resource_type}{entity_suffix.lower().replace(' ', '_')}"
        icon = get_resource_icon(resource_type)
        
        super().__init__(coordinator, name, unique_id, icon)
    
    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"
    
    def get_resource_data(self):
        """Get resource data for this domain."""
        return self.safe_get_data("domain_resources", self._domain_id, default={})


class VCFHostResourceBaseSensor(VCFResourceBaseSensor):
    """Base class for host resource sensors."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix, 
                 host_id, hostname, resource_type):
        self._host_id = host_id
        self._hostname = hostname        
        entity_suffix = f" {hostname}"
        super().__init__(coordinator, domain_id, domain_name, domain_prefix, 
                        resource_type, entity_suffix)
        
        # Override unique_id to include host info
        safe_domain_name = safe_name_conversion(domain_name)
        safe_hostname = safe_name_conversion(hostname)
        self._attr_unique_id = f"vcf_{domain_prefix}_{safe_domain_name}_{safe_hostname}_{resource_type}"
    
    def get_host_data(self):
        """Get data for this specific host."""
        try:
            domain_resources = self.safe_get_data("domain_resources", self._domain_id, default={})
            if not domain_resources:
                _LOGGER.debug(f"No domain resources found for host {self._hostname}")
                return {}
            
            clusters = domain_resources.get("clusters", [])
            
            for cluster in clusters:
                hosts = cluster.get("hosts", [])
                for host in hosts:
                    if host.get("id") == self._host_id:
                        return host
            
            _LOGGER.debug(f"Host {self._hostname} (ID: {self._host_id}) not found in domain resources")
            return {}
        except Exception as e:
            _LOGGER.warning(f"Error getting host data for {self._hostname}: {e}")
            return {}
    
    @property
    def state(self):
        """Return the usage percentage for this host resource."""
        try:
            host_data = self.get_host_data()
            resource_info = host_data.get(self._resource_type, {})
            
            if self._resource_type == "cpu":
                used_mhz = resource_info.get("used_mhz", 0)
                total_mhz = resource_info.get("total_mhz", 1)
                return round((used_mhz / total_mhz) * 100, 1) if total_mhz > 0 else 0
            
            elif self._resource_type in ["memory", "storage"]:
                used_mb = resource_info.get("used_mb", 0)
                total_mb = resource_info.get("total_mb", 1)
                return round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0
            
            return 0
        except Exception as e:
            _LOGGER.error(f"Error getting {self._resource_type} state for host {self._hostname}: {e}")
            return 0
    
    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        try:
            host_data = self.get_host_data()
            resource_info = host_data.get(self._resource_type, {})
            
            attributes = {
                "domain": self._domain_name,
                "domain_prefix": self._domain_prefix,
                "hostname": self._hostname,
                "host_id": self._host_id,
                "resource_type": self._resource_type,
                "fqdn": host_data.get("fqdn", "Unknown")
            }
            
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
            
            return attributes
            
        except Exception as e:
            _LOGGER.error(f"Error getting {self._resource_type} attributes for host {self._hostname}: {e}")
            return {"error": str(e)}
