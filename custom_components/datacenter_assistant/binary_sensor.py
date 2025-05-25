from homeassistant.components.binary_sensor import BinarySensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class VCFUpgradeBinarySensor(BinarySensorEntity):
    """Binary sensor to indicate if an upgrade is available."""

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "VCF Upgrades Available"

    @property
    def is_on(self):
        try:
            return any(
                b.get("status") == "AVAILABLE"
                for b in self.coordinator.data["upgradable_data"].get("elements", [])
            )
        except Exception as e:
            _LOGGER.warning("Failed to check VCF upgrade availability: %s", e)
            return False
