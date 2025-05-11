from homeassistant.components.binary_sensor import BinarySensorEntity

class VCFUpgradeBinarySensor(BinarySensorEntity):
    """Binary sensor to indicate if an upgrade is available."""

    def __init__(self, coordinator):
        """Initialize the binary sensor."""
        self.coordinator = coordinator

    @property
    def name(self):
        return "VCF Upgrades Available"

    @property
    def is_on(self):
        """Return True if any upgrades are available."""
        return any(b["status"] == "AVAILABLE" for b in self.coordinator.data["upgradable_data"]["elements"])