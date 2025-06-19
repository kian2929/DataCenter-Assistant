import logging
import asyncio
import time
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import get_coordinator
from .vcf_api import VCFAPIClient

_LOGGER = logging.getLogger(__name__)
_DOMAIN = "datacenter_assistant"


class VCFButtonManager:
    """Manager class for VCF button entities."""
    
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.vcf_client = VCFAPIClient(hass, entry)
    
    def create_buttons(self, coordinator):
        """Create all VCF button entities."""
        return [
            VCFRefreshTokenButton(self.hass, self.entry, self.vcf_client),
            VCFManualUpdateCheckButton(self.hass, self.entry, coordinator)
        ]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the button platform using OOP approach."""
    coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    button_manager = VCFButtonManager(hass, entry)
    entities = button_manager.create_buttons(coordinator)
    
    async_add_entities(entities)


class VCFRefreshTokenButton(ButtonEntity):
    """Button to refresh VCF token manually using API client."""
    
    def __init__(self, hass, entry, vcf_client):
        self.hass = hass
        self.entry = entry
        self.vcf_client = vcf_client
        self._attr_name = "VCF Refresh Token"
        self._attr_unique_id = f"{entry.entry_id}_vcf_manual_refresh"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:refresh-circle"
    
    async def async_press(self) -> None:
        """Handle button press to refresh token using API client."""
        _LOGGER.info("Manually refreshing VCF token")
        
        try:
            # Use the API client's refresh method
            new_token = await self.vcf_client.refresh_token()
            
            if new_token:
                # Force update the coordinator to use the new token
                coordinator = self.hass.data.get(_DOMAIN, {}).get("coordinator")
                if coordinator:
                    await coordinator.async_refresh()
                _LOGGER.info("VCF token refreshed successfully")
            else:
                _LOGGER.warning("Failed to refresh VCF token")
                
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")


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

