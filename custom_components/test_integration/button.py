from homeassistant.components.button import ButtonEntity

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the custom button platform."""
    async_add_entities([ExampleButton()])

class ExampleButton(ButtonEntity):
    """Example Button Entity."""

    def __init__(self):
        self._attr_name = "Mein Testbutton"
        self._attr_unique_id = "mein_testbutton"

    async def async_press(self) -> None:
        """Handle the button press."""
        print("Der Button wurde gedrückt!")
