from homeassistant.components.binary_sensor import BinarySensorEntity

class VCFUpgradeBinarySensor(BinarySensorEntity):
    """Binary sensor to indicate if an upgrade is available."""

    def __init__(self, coordinator):
        """Initialize the binary sensor."""
        self.coordinator = coordinator
        self._attr_name = "VCF Upgrades Available"
        self._attr_unique_id = "vcf_upgrades_available"

    #test
    @property
    def is_on(self):
        """Return True if any upgrades are available."""
        upgrades = self.coordinator.data.get("upgradable_data", {}).get("elements", [])
        return any(up["status"] == "AVAILABLE" for up in upgrades)
