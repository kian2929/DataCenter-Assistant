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
from .upgrade_service import VCFUpgradeService

_LOGGER = logging.getLogger(__name__)
_DOMAIN = "datacenter_assistant"


class VCFButtonManager:
    """Manager class for VCF button entities."""
    
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.vcf_client = VCFAPIClient(hass, entry)
        self.upgrade_service = VCFUpgradeService(hass, entry, self.vcf_client)
        
        # Store upgrade service in hass data for access by other components
        hass.data.setdefault(_DOMAIN, {})["upgrade_service"] = self.upgrade_service


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the button platform using OOP approach."""
    coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    button_manager = VCFButtonManager(hass, entry)
    
    # Create initial static buttons
    static_buttons = [
        VCFRefreshTokenButton(hass, entry, button_manager.vcf_client),
        VCFManualUpdateCheckButton(hass, entry, coordinator)
    ]
    
    async_add_entities(static_buttons)
    
    # Store button manager and async_add_entities for dynamic button creation
    hass.data.setdefault(_DOMAIN, {})["button_manager"] = button_manager
    hass.data.setdefault(_DOMAIN, {})["button_async_add_entities"] = async_add_entities
    
    # Set up dynamic button creation when coordinator data changes
    existing_domain_buttons = set()
    
    async def create_domain_buttons():
        """Create domain-specific buttons dynamically."""
        if coordinator.data and coordinator.data.get("domain_updates"):
            new_buttons = []
            for domain_id, domain_data in coordinator.data["domain_updates"].items():
                if domain_id not in existing_domain_buttons:
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_domain_buttons) + 1}")
                    
                    new_buttons.extend([
                        VCFDomainUpgradeButton(hass, entry, coordinator, button_manager.upgrade_service, 
                                             domain_id, domain_name, domain_prefix),
                        VCFDomainAcknowledgeButton(hass, entry, coordinator, button_manager.upgrade_service, 
                                                 domain_id, domain_name, domain_prefix)
                    ])
                    existing_domain_buttons.add(domain_id)
            
            if new_buttons:
                _LOGGER.info(f"Adding {len(new_buttons)} domain buttons")
                async_add_entities(new_buttons, True)
    
    # Add listener for coordinator updates
    def coordinator_update_callback():
        hass.async_create_task(create_domain_buttons())
    
    coordinator.async_add_listener(coordinator_update_callback)
    
    # Schedule initial button creation
    hass.loop.call_later(2.0, lambda: hass.async_create_task(create_domain_buttons()))


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


class VCFDomainUpgradeButton(ButtonEntity, CoordinatorEntity):
    """Button to start VCF upgrade for a specific domain."""
    
    def __init__(self, hass, entry, coordinator, upgrade_service, domain_id, domain_name, domain_prefix):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.upgrade_service = upgrade_service
        self.domain_id = domain_id
        self.domain_name = domain_name
        self.domain_prefix = domain_prefix
        self._attr_name = f"VCF {domain_name} Start Upgrade"
        self._attr_unique_id = f"{entry.entry_id}_vcf_{domain_prefix}_start_upgrade"
        self._attr_icon = "mdi:rocket-launch"
    
    async def async_press(self) -> None:
        """Handle button press to start VCF upgrade."""
        _LOGGER.info(f"Starting VCF upgrade for domain {self.domain_name}")
        
        try:
            domain_data = self.coordinator.data.get("domain_updates", {}).get(self.domain_id, {})
            success = await self.upgrade_service.start_upgrade(self.domain_id, domain_data)
            
            if success:
                _LOGGER.info(f"VCF upgrade started successfully for domain {self.domain_name}")
            else:
                _LOGGER.warning(f"VCF upgrade could not be started for domain {self.domain_name}")
                
        except Exception as e:
            _LOGGER.error(f"Error starting VCF upgrade for domain {self.domain_name}: {e}")


class VCFDomainAcknowledgeButton(ButtonEntity, CoordinatorEntity):
    """Button to acknowledge alerts during VCF upgrade."""
    
    def __init__(self, hass, entry, coordinator, upgrade_service, domain_id, domain_name, domain_prefix):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.upgrade_service = upgrade_service
        self.domain_id = domain_id
        self.domain_name = domain_name
        self.domain_prefix = domain_prefix
        self._attr_name = f"VCF {domain_name} Acknowledge Alerts"
        self._attr_unique_id = f"{entry.entry_id}_vcf_{domain_prefix}_acknowledge_alerts"
        self._attr_icon = "mdi:check-circle"
    
    async def async_press(self) -> None:
        """Handle button press to acknowledge alerts."""
        _LOGGER.info(f"Acknowledging alerts for domain {self.domain_name}")
        
        try:
            success = await self.upgrade_service.acknowledge_alerts(self.domain_id)
            
            if success:
                _LOGGER.info(f"Alerts acknowledged successfully for domain {self.domain_name}")
            else:
                _LOGGER.warning(f"No alerts to acknowledge for domain {self.domain_name}")
                
        except Exception as e:
            _LOGGER.error(f"Error acknowledging alerts for domain {self.domain_name}: {e}")

