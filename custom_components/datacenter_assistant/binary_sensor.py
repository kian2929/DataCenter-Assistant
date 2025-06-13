import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up binary sensors for VCF system status."""
    try:
        # Get or create coordinator
        coordinator = hass.data.get("datacenter_assistant", {}).get("coordinator")
        
        if not coordinator:
            coordinator = get_coordinator(hass, config_entry)
            hass.data.setdefault("datacenter_assistant", {})["coordinator"] = coordinator
            
        await coordinator.async_config_entry_first_refresh()
        
        # Create binary sensors
        entities = [
            VCFConnectionBinarySensor(coordinator),
            VCFUpdatesAvailableBinarySensor(coordinator)
        ]
        
        async_add_entities(entities, True)
    except Exception as e:
        _LOGGER.warning("Could not set up VCF binary sensors: %s", e)


class VCFConnectionBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor to indicate VCF connection status."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Connection"
        self._attr_unique_id = "vcf_connection"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:server-network"

    @property
    def is_on(self):
        """Return True if VCF is connected and domains are available."""
        try:
            if self.coordinator.data is None:
                return False
                
            # Check if we have domain data and no setup failed
            domains = self.coordinator.data.get("domains", [])
            setup_failed = self.coordinator.data.get("setup_failed", False)
            
            return len(domains) > 0 and not setup_failed
        except Exception as e:
            _LOGGER.warning("Failed to check VCF connection: %s", e)
            return False

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        try:
            if not self.coordinator.data:
                return {"error": "No data available"}
                
            domains = self.coordinator.data.get("domains", [])
            setup_failed = self.coordinator.data.get("setup_failed", False)
            
            attributes = {
                "domain_count": len(domains),
                "setup_failed": setup_failed,
            }
            
            # Add last successful update time in readable format
            if self.coordinator.last_update_success:
                from datetime import datetime
                last_update_time = datetime.fromtimestamp(self.coordinator.last_update_success).strftime("%Y-%m-%d %H:%M:%S")
                attributes["last_successful_update"] = last_update_time
            else:
                attributes["last_successful_update"] = "Never"
            
            # Only add error if there actually is one
            coordinator_error = self.coordinator.data.get("error") if self.coordinator.data else None
            if coordinator_error:
                attributes["connection_error"] = coordinator_error
                
            return attributes
        except Exception as e:
            return {"error": str(e)}


class VCFUpdatesAvailableBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor to indicate if any VCF updates are available across all domains."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "VCF Updates Available"
        self._attr_unique_id = "vcf_updates_available"
        self._attr_device_class = BinarySensorDeviceClass.UPDATE
        self._attr_icon = "mdi:update"

    @property
    def is_on(self):
        """Return True if any domain has updates available."""
        try:
            if not self.coordinator.data:
                return False
                
            domain_updates = self.coordinator.data.get("domain_updates", {})
            
            # Check if any domain has updates available
            for domain_data in domain_updates.values():
                if domain_data.get("update_status") == "updates_available":
                    return True
                    
            return False
        except Exception as e:
            _LOGGER.warning("Failed to check VCF update availability: %s", e)
            return False

    @property
    def extra_state_attributes(self):
        """Return additional attributes about available updates."""
        try:
            if not self.coordinator.data:
                return {"error": "No data available"}
                
            domain_updates = self.coordinator.data.get("domain_updates", {})
            
            # Count domains by status
            status_counts = {
                "updates_available": 0,
                "up_to_date": 0,
                "error": 0,
                "unknown": 0
            }
            
            domains_with_updates = []
            
            for domain_id, domain_data in domain_updates.items():
                status = domain_data.get("update_status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
                
                if status == "updates_available":
                    next_version = domain_data.get("next_version", {})
                    domains_with_updates.append({
                        "domain_name": domain_data.get("domain_name"),
                        "current_version": domain_data.get("current_version"),
                        "next_version": next_version.get("versionNumber"),
                        "components_with_updates": len(domain_data.get("component_updates", {}))
                    })
            
            return {
                "total_domains": len(domain_updates),
                "domains_with_updates": status_counts["updates_available"],
                "domains_up_to_date": status_counts["up_to_date"],
                "domains_with_errors": status_counts["error"],
                "update_details": domains_with_updates
            }
        except Exception as e:
            return {"error": str(e)}
