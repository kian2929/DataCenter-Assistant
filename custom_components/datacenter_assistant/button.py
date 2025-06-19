import logging
import time
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)
_DOMAIN = "datacenter_assistant"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the button platform."""
    coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    entities = [
        VCFRefreshTokenButton(hass, entry),
        VCFManualUpdateCheckButton(hass, entry, coordinator)
    ]
    
    async_add_entities(entities)


async def _refresh_token_helper(hass: HomeAssistant, entry: ConfigEntry):
    """Helper function to refresh VCF token."""
    vcf_url = entry.data.get("vcf_url")
    vcf_username = entry.data.get("vcf_username", "")
    vcf_password = entry.data.get("vcf_password", "")
    
    if not all([vcf_url, vcf_username, vcf_password]):
        _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
        return False
        
    try:
        session = async_get_clientsession(hass)
        auth_data = {"username": vcf_username, "password": vcf_password}
        
        _LOGGER.info(f"Attempting to connect to {vcf_url}/v1/tokens")
        
        async with session.post(f"{vcf_url}/v1/tokens", json=auth_data, ssl=False) as resp:
            if resp.status != 200:
                _LOGGER.error(f"VCF token refresh failed: {resp.status}")
                return False
                
            token_data = await resp.json()
            new_token = token_data.get("accessToken") or token_data.get("access_token")
            
            if new_token:
                new_data = dict(entry.data)
                expiry = int(time.time()) + 3600
                new_data.update({"vcf_token": new_token, "token_expiry": expiry})
                
                _LOGGER.info(f"New token will expire at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))}")
                hass.config_entries.async_update_entry(entry, data=new_data)
                return True
            else:
                _LOGGER.warning("Could not extract token from response")
                return False
                
    except Exception as e:
        _LOGGER.error(f"Error refreshing VCF token: {e}")
        return False


class VCFRefreshTokenButton(ButtonEntity):
    """Button to refresh VCF token manually."""
    
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._attr_name = "VCF Refresh Token"
        self._attr_unique_id = f"{entry.entry_id}_vcf_refresh_token_button"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:refresh-circle"
    
    async def async_press(self) -> None:
        """Handle button press to refresh token."""
        _LOGGER.info("Manually refreshing VCF token")
        
        success = await _refresh_token_helper(self.hass, self.entry)
        
        if success:
            # Force update of coordinator
            coordinator = self.hass.data.get(_DOMAIN, {}).get("coordinator")
            if coordinator:
                await coordinator.async_refresh()


class VCFManualUpdateCheckButton(ButtonEntity, CoordinatorEntity):
    """Button to manually trigger VCF update check process."""
    
    def __init__(self, hass, entry, coordinator):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._attr_name = "VCF Manual Update Check"
        self._attr_unique_id = f"{entry.entry_id}_vcf_manual_update_check"
        self._attr_icon = "mdi:magnify"
    
    async def async_press(self) -> None:
        """Handle button press to manually trigger update check."""
        _LOGGER.info("Manually triggering VCF update check process")
        
        try:
            # Force coordinator refresh to run the update check workflow
            await self.coordinator.async_refresh()
            _LOGGER.info("VCF update check process completed successfully")
        except Exception as e:
            _LOGGER.error(f"Error during manual VCF update check: {e}")

