import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
_DOMAIN = "datacenter_assistant"


class VCFBinarySensorManager:
    """Manager class for VCF binary sensor entities."""
    
    def __init__(self, coordinator):
        self.coordinator = coordinator
    
    def create_binary_sensors(self):
        """Create all VCF binary sensor entities."""
        return [
            VCFConnectionBinarySensor(self.coordinator),
            VCFUpdatesAvailableBinarySensor(self.coordinator)
        ]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up binary sensors for VCF system status using OOP approach."""
    try:
        # Get or create coordinator
        coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
        
        if not coordinator:
            coordinator = get_coordinator(hass, config_entry)
            hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
            
        await coordinator.async_config_entry_first_refresh()
        
        # Create binary sensors using manager
        sensor_manager = VCFBinarySensorManager(coordinator)
        entities = sensor_manager.create_binary_sensors()
        
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
        
        # State preservation during expected API outages
        self._last_known_state = None
        self._api_outage_active = False
        
        # Listen for API outage events
        self._remove_listeners = []
    
    async def async_added_to_hass(self):
        """Run when sensor is added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Listen for API outage events
        self._remove_listeners.append(
            self.hass.bus.async_listen("vcf_api_outage_expected", self._handle_api_outage_expected)
        )
        self._remove_listeners.append(
            self.hass.bus.async_listen("vcf_api_restored", self._handle_api_restored)
        )
    
    async def async_will_remove_from_hass(self):
        """Run when sensor is removed from Home Assistant."""
        for remove_listener in self._remove_listeners:
            remove_listener()
    
    def _handle_api_outage_expected(self, event):
        """Handle notification of expected API outage."""
        reason = event.data.get("reason", "unknown")
        if reason == "sddc_manager_upgrade":
            _LOGGER.info("VCF Connection sensor: Preserving connection state during SDDC Manager upgrade")
            self._last_known_state = self._get_connection_state()
            self._api_outage_active = True
            self.async_schedule_update_ha_state()
    
    def _handle_api_restored(self, event):
        """Handle notification of API restoration."""
        reason = event.data.get("reason", "unknown")
        _LOGGER.info(f"VCF Connection sensor: API restored, reason: {reason}")
        self._api_outage_active = False
        self._last_known_state = None
        self.async_schedule_update_ha_state()
    
    def _get_connection_state(self):
        """Get the actual connection state from coordinator data."""
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
    def is_on(self):
        """Return True if VCF is connected and domains are available."""
        # During expected API outage, preserve the last known state
        if self._api_outage_active and self._last_known_state is not None:
            return self._last_known_state
        
        return self._get_connection_state()

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        try:
            attributes = {}
            
            # If we're in an API outage, indicate this in attributes
            if self._api_outage_active:
                attributes["api_outage_active"] = True
                attributes["outage_reason"] = "SDDC Manager upgrade in progress"
                attributes["state_preserved"] = True
                
                # If we have last known data, use it
                if self._last_known_state is not None:
                    attributes["using_preserved_state"] = True
                
                return attributes
            
            if not self.coordinator.data:
                return {"error": "No data available"}
                
            domains = self.coordinator.data.get("domains", [])
            setup_failed = self.coordinator.data.get("setup_failed", False)
            
            attributes.update({
                "domain_count": len(domains),
                "setup_failed": setup_failed,
                "api_outage_active": False
            })
            
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
                    next_release = domain_data.get("next_release", {})
                    domains_with_updates.append({
                        "domainName": domain_data.get("domain_name"),
                        "current_version": domain_data.get("current_version"),
                        "next_version": next_release.get("version")
                    })
            
            return {
                "total_domains": len(domain_updates),
                "domains_with_updates": status_counts["updates_available"],
                "domains_up_to_date": status_counts["up_to_date"],
                "domains_with_errors": status_counts["error"],
                "update_details": domains_with_updates
            }
        except Exception as e:
            _LOGGER.error(f"Error getting update availability attributes: {e}")
            return {"error": str(e)}
