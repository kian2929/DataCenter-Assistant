from homeassistant.components.binary_sensor import BinarySensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class VCFUpgradeBinarySensor(BinarySensorEntity):
    """Binary sensor to indicate if a VCF upgrade is available."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrades Available"
        self._attr_unique_id = "vcf_upgrades_available"

    @property
    def is_on(self):
        """Return true if at least one upgrade is available."""
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return any(b.get("status") == "AVAILABLE" for b in data)
        except Exception as e:
            _LOGGER.warning("Failed to check VCF upgrade availability: %s", e)
            return False

    @property
    def available(self):
        """Return False if connection/data is invalid — sensor unavailable in HA."""
        try:
            data = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
            return bool(data)
        except Exception as e:
            _LOGGER.warning("VCF BinarySensor not available: %s", e)
            return False

    @property
    def extra_state_attributes(self):
        """Additional details for troubleshooting."""
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
