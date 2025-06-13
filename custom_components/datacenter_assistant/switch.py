import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry  
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
_DOMAIN = "datacenter_assistant"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the switch platform."""
    coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    # Wait for coordinator to have data to create domain-specific switches
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Switch coordinator first refresh failed: %s", e)
    
    entities = []
    
    # Store reference for dynamic entity creation
    hass.data.setdefault(_DOMAIN, {})["switch_async_add_entities"] = async_add_entities
    
    # Keep track of existing domain switches to avoid duplicates
    existing_domain_switches = set()
    
    def _coordinator_update_callback():
        """Listen for coordinator updates and create switches for new domains."""
        if coordinator.data and "domain_updates" in coordinator.data:
            new_entities = []
            for domain_id, domain_data in coordinator.data["domain_updates"].items():
                # Check if we already have switches for this domain
                if domain_id not in existing_domain_switches:
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_domain_switches) + 1}")
                    
                    _LOGGER.info(f"Creating switches for newly discovered domain: {domain_name} with prefix: {domain_prefix}")
                    
                    new_entities.append(
                        VCFDomainIgnoreAlertsSwitch(coordinator, domain_id, domain_name, domain_prefix)
                    )
                    
                    # Mark this domain as having switches
                    existing_domain_switches.add(domain_id)
            
            if new_entities:
                _LOGGER.info(f"Adding {len(new_entities)} switches for newly discovered domains")
                async_add_entities(new_entities, True)
    
    # Add listener for coordinator updates
    coordinator.async_add_listener(_coordinator_update_callback)
    
    # Schedule domain-specific switch creation after coordinator data is available
    async def _add_domain_switches():
        """Add domain-specific switches after data is available."""
        await coordinator.async_request_refresh()  # Ensure we have fresh data
        
        if coordinator.data and "domain_updates" in coordinator.data:
            new_entities = []
            for i, (domain_id, domain_data) in enumerate(coordinator.data["domain_updates"].items()):
                domain_name = domain_data.get("domain_name", "Unknown")
                domain_prefix = domain_data.get("domain_prefix", f"domain{i + 1}")
                
                _LOGGER.info(f"Creating switches for domain: {domain_name} with prefix: {domain_prefix}")
                
                new_entities.append(
                    VCFDomainIgnoreAlertsSwitch(coordinator, domain_id, domain_name, domain_prefix)
                )
                
                # Mark this domain as having switches
                existing_domain_switches.add(domain_id)
            
            if new_entities:
                _LOGGER.info(f"Adding {len(new_entities)} switches for initial domains")
                async_add_entities(new_entities, True)
    
    # Schedule the domain switches creation
    hass.async_create_task(_add_domain_switches())


class VCFDomainIgnoreAlertsSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to control whether to ignore alerts during upgrades for a specific domain."""
    
    def __init__(self, coordinator, domain_id, domain_name, domain_prefix=None):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain{domain_id[:8]}"
        
        # Entity naming with space
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} Ignore Alerts"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_name}_ignore_alerts"
        self._attr_icon = "mdi:alert-circle-outline"
        self._attr_entity_category = EntityCategory.CONFIG
        
        # Default state is OFF (do not ignore alerts)
        self._is_on = False
    
    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on - ignore alerts during upgrades."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info(f"Domain {self._domain_name}: Ignore alerts enabled")
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off - do not ignore alerts during upgrades."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info(f"Domain {self._domain_name}: Ignore alerts disabled")
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "domain": self._domain_name,
            "domain_id": self._domain_id,
            "purpose": "Control whether to ignore alerts during upgrades"
        }
