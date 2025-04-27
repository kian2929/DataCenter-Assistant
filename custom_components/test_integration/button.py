from homeassistant.components.button import ButtonEntity

async def async_setup_entry(hass, config_entry, async_add_entities):
    async_add_entities([ExampleButton()])

class ExampleButton(ButtonEntity):
    """Example Button Entity."""

    def __init__(self):
        self._attr_name = "Mein Testbutton"
        self._attr_unique_id = "mein_testbutton"

    async def async_press(self) -> None:
        """Handle the button press."""
        print("Der Button wurde gedrückt!!")
