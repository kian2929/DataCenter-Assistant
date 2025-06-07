import logging
import voluptuous as vol
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the button platform."""
    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(DOMAIN, {})["coordinator"] = coordinator
    
    entities = [
        VCFRefreshTokenButton(hass, entry),
        VCFExecuteUpdatesButton(hass, entry, coordinator)
    ]
    
    async_add_entities(entities)


class VCFRefreshTokenButton(ButtonEntity):
    """Button to refresh VCF token manually."""
    
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._attr_name = "VCF Refresh Token"
        self._attr_unique_id = f"{entry.entry_id}_vcf_refresh_token"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:refresh-circle"
    
    async def async_press(self) -> None:
        """Handle button press to refresh token."""
        _LOGGER.info("Manually refreshing VCF token")
        
        vcf_url = self.entry.data.get("vcf_url")
        vcf_username = self.entry.data.get("vcf_username", "")
        vcf_password = self.entry.data.get("vcf_password", "")
        
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
            return
            
        try:
            # Direkter API-Aufruf für Token-Erneuerung
            import time
            session = async_get_clientsession(self.hass)
            login_url = f"{vcf_url}/v1/tokens"
            
            auth_data = {
                "username": vcf_username,
                "password": vcf_password
            }
            
            async with session.post(login_url, json=auth_data, ssl=False) as resp:
                if resp.status != 200:
                    _LOGGER.error(f"VCF token refresh failed: {resp.status}")
                    return
                    
                token_data = await resp.json()
                new_token = token_data.get("accessToken") or token_data.get("access_token")
                
                if new_token:
                    # Aktualisiere die Konfiguration mit neuem Token und Ablaufzeit
                    new_data = dict(self.entry.data)
                    new_data["vcf_token"] = new_token
                    
                    # Token-Ablaufzeit berechnen (1 Stunde ab jetzt)
                    expiry = int(time.time()) + 3600  # 1 Stunde in Sekunden
                    new_data["token_expiry"] = expiry
                    _LOGGER.info(f"New token will expire at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))}")
                    
                    self.hass.config_entries.async_update_entry(
                        self.entry, 
                        data=new_data
                    )
                    
                    # Force update des Coordinators
                    coordinator = self.hass.data.get(DOMAIN, {}).get("coordinator")
                    if coordinator:
                        await coordinator.async_refresh()
                else:
                    _LOGGER.warning("Could not extract token from response")
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")


class VCFExecuteUpdatesButton(ButtonEntity, CoordinatorEntity):
    """Button to execute VCF updates."""
    
    def __init__(self, hass, entry, coordinator):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._attr_name = "VCF Execute Updates"
        self._attr_unique_id = f"{entry.entry_id}_vcf_execute_updates"
        self._attr_icon = "mdi:update"
    
    @property
    def available(self):
        """Return if button is available."""
        # Nur verfügbar, wenn Updates vorhanden sind
        try:
            if self.coordinator.data and "upgradable_data" in self.coordinator.data:
                elements = self.coordinator.data["upgradable_data"].get("elements", [])
                return any(item.get("status") == "AVAILABLE" for item in elements)
        except Exception:
            pass
        return False
    
    async def async_press(self) -> None:
        """Handle button press to execute updates."""
        _LOGGER.info("Starting VCF update execution")
        
        vcf_url = self.entry.data.get("vcf_url")
        current_token = self.entry.data.get("vcf_token")
        
        if not vcf_url or not current_token:
            _LOGGER.warning("Cannot execute updates: Missing URL or token")
            return
        
        # Holen der verfügbaren Updates
        available_updates = []
        if self.coordinator.data and "upgradable_data" in self.coordinator.data:
            elements = self.coordinator.data["upgradable_data"].get("elements", [])
            available_updates = [item for item in elements if item.get("status") == "AVAILABLE"]
        
        if not available_updates:
            _LOGGER.info("No updates available to execute")
            return
        
        try:
            session = async_get_clientsession(self.hass)
            
            # Für jedes verfügbare Update einen API-Aufruf machen
            for update in available_updates:
                resource = update.get("resource", {})
                fqdn = resource.get("fqdn", "")
                component_type = resource.get("type", "")
                
                if not fqdn or not component_type:
                    continue
                
                # API-Endpunkt für Update-Ausführung
                api_url = f"{vcf_url}/v1/system/updates/{component_type.lower()}/{fqdn}/start"
                
                headers = {
                    "Authorization": f"Bearer {current_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                _LOGGER.info(f"Starting update for {component_type} {fqdn}")
                
                async with session.post(api_url, headers=headers, json={}, ssl=False) as resp:
                    if resp.status == 401:
                        _LOGGER.warning("Token expired during update execution, please refresh token and try again")
                        break
                    elif resp.status != 202 and resp.status != 200:  # 202 Accepted ist typisch für asynchrone Operationen
                        error_text = await resp.text()
                        _LOGGER.error(f"Failed to start update for {component_type} {fqdn}: {resp.status} {error_text}")
                    else:
                        _LOGGER.info(f"Successfully initiated update for {component_type} {fqdn}")
            
            # Aktualisieren des Coordinators nach dem Start der Updates
            await self.coordinator.async_refresh()
                
        except Exception as e:
            _LOGGER.error(f"Error executing VCF updates: {e}")