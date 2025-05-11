from homeassistant.components.button import ButtonEntity
from .coordinator import get_coordinator

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = get_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([VCFUpgradeTriggerButton(coordinator)])

class VCFUpgradeTriggerButton(ButtonEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "Perform VCF Upgrade"

    async def async_press(self):
        # Replace with real upgrade trigger logic
        _LOGGER.warning("Upgrade button pressed. Add real logic here.")