import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "test_integration"
SERVICE_RUN = "run_test"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Test Integration."""
    async def handle_run_test(call):
        _LOGGER.info("Der Test-Service wurde aufgerufen und funktioniert!")

    hass.services.async_register(
        DOMAIN, SERVICE_RUN, handle_run_test
    )

    _LOGGER.info("Test Integration geladen!")
    return True
