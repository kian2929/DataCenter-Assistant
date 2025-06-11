import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up binary sensors for VCF upgrade availability."""
    try:
        # Get or create coordinator
        coordinator = hass.data.get("datacenter_assistant", {}).get("coordinator")
        
        if not coordinator:
            coordinator = get_coordinator(hass, config_entry)
            hass.data.setdefault("datacenter_assistant", {})["coordinator"] = coordinator
            
        await coordinator.async_config_entry_first_refresh()
        entity = VCFUpgradeBinarySensor(coordinator)
        async_add_entities([entity], True)
    except Exception as e:
        _LOGGER.warning("Could not set up VCF binary sensor: %s", e)


class VCFUpgradeBinarySensor(BinarySensorEntity):
    """Binary sensor to indicate if a VCF upgrade is available."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrades Available"
        self._attr_unique_id = "vcf_upgrades_available"

    @property
    def is_on(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return any(b.get("status") == "AVAILABLE" for b in data)
        except Exception as e:
            _LOGGER.warning("Failed to check VCF upgrade availability: %s", e)
            return False

    @property
    def available(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return bool(data)
        except Exception as e:
            _LOGGER.warning("VCF BinarySensor not available: %s", e)
            return False
        
        

    @property
    def extra_state_attributes(self):
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return {
                "raw_statuses": [x.get("status") for x in data],
                "connected": True if data else False
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }
