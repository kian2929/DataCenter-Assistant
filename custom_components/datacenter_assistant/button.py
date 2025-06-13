import logging
import asyncio
import voluptuous as vol
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
_DOMAIN = "datacenter_assistant"  # Lokale Variable anstatt Import

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the button platform."""
    coordinator = hass.data.get(_DOMAIN, {}).get("coordinator")
    
    if not coordinator:
        coordinator = get_coordinator(hass, entry)
        hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    # Wait for coordinator to have data to create domain-specific buttons
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Button coordinator first refresh failed: %s", e)
    
    entities = [
        VCFRefreshTokenButton(hass, entry),
        VCFManualUpdateCheckButton(hass, entry, coordinator),
        VCFExecuteUpdatesButton(hass, entry, coordinator),
        VCFDownloadBundleButton(hass, entry, coordinator)
    ]
    
    # Store reference for dynamic entity creation
    hass.data.setdefault(_DOMAIN, {})["button_async_add_entities"] = async_add_entities
    
    # Keep track of existing domain buttons to avoid duplicates
    existing_domain_buttons = set()
    
    def _coordinator_update_callback():
        """Listen for coordinator updates and create buttons for new domains."""
        if coordinator.data and "domain_updates" in coordinator.data:
            new_entities = []
            for domain_id, domain_data in coordinator.data["domain_updates"].items():
                # Check if we already have buttons for this domain
                if domain_id not in existing_domain_buttons:
                    domain_name = domain_data.get("domain_name", "Unknown")
                    domain_prefix = domain_data.get("domain_prefix", f"domain{len(existing_domain_buttons) + 1}")
                    
                    _LOGGER.info(f"Creating buttons for newly discovered domain: {domain_name} with prefix: {domain_prefix}")
                    
                    new_entities.extend([
                        VCFDomainUpgradeButton(hass, entry, coordinator, domain_id, domain_name, domain_prefix),
                        VCFDomainAcknowledgeAlertsButton(hass, entry, coordinator, domain_id, domain_name, domain_prefix)
                    ])
                    
                    # Mark this domain as having buttons
                    existing_domain_buttons.add(domain_id)
            
            if new_entities:
                _LOGGER.info(f"Adding {len(new_entities)} buttons for newly discovered domains")
                async_add_entities(new_entities, True)
    
    # Add listener for coordinator updates
    coordinator.async_add_listener(_coordinator_update_callback)
    
    # Schedule domain-specific button creation after coordinator data is available
    async def _add_domain_buttons():
        """Add domain-specific buttons after data is available."""
        await coordinator.async_request_refresh()  # Ensure we have fresh data
        
        if coordinator.data and "domain_updates" in coordinator.data:
            new_entities = []
            for i, (domain_id, domain_data) in enumerate(coordinator.data["domain_updates"].items()):
                domain_name = domain_data.get("domain_name", "Unknown")
                domain_prefix = domain_data.get("domain_prefix", f"domain{i + 1}")
                
                _LOGGER.info(f"Creating buttons for domain: {domain_name} with prefix: {domain_prefix}")
                
                new_entities.extend([
                    VCFDomainUpgradeButton(hass, entry, coordinator, domain_id, domain_name, domain_prefix),
                    VCFDomainAcknowledgeAlertsButton(hass, entry, coordinator, domain_id, domain_name, domain_prefix)
                ])
                
                # Mark this domain as having buttons
                existing_domain_buttons.add(domain_id)
            
            if new_entities:
                _LOGGER.info(f"Adding {len(new_entities)} buttons for initial domains")
                entities.extend(new_entities)
    
    # Schedule the domain buttons creation
    hass.async_create_task(_add_domain_buttons())
    
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
            session = async_get_clientsession(self.hass)
            login_url = f"{vcf_url}/v1/tokens"
            
            auth_data = {
                "username": vcf_username,
                "password": vcf_password
            }
            
            _LOGGER.info(f"Attempting to connect to {login_url}")
            
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
                    coordinator = self.hass.data.get(_DOMAIN, {}).get("coordinator")
                    if coordinator:
                        await coordinator.async_refresh()
                else:
                    _LOGGER.warning("Could not extract token from response")
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")


class VCFManualUpdateCheckButton(ButtonEntity, CoordinatorEntity):
    """Button to manually trigger VCF update check process as per flow.txt."""
    
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
                    _LOGGER.warning(f"Skipping update with missing fqdn or component_type: {update}")
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


class VCFDownloadBundleButton(ButtonEntity, CoordinatorEntity):
    """Button to download selected VCF bundle."""
    
    def __init__(self, hass, entry, coordinator, bundle_id=None):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._bundle_id = bundle_id  # Optional: Um einen spezifischen Bundle herunterzuladen
        self._attr_name = "VCF Download Bundle"
        self._attr_unique_id = f"{entry.entry_id}_vcf_download_bundle"
        self._attr_icon = "mdi:package-down"
    
    @property
    def available(self):
        """Button ist verfügbar, wenn Bundles existieren."""
        if not self.coordinator.data or "bundle_data" not in self.coordinator.data:
            return False
        
        bundles = self.coordinator.data["bundle_data"].get("elements", [])
        return len(bundles) > 0
    
    async def async_press(self) -> None:
        """Handle button press to download VCF bundle."""
        _LOGGER.info("Starting VCF bundle download")
        
        vcf_url = self.entry.data.get("vcf_url")
        current_token = self.entry.data.get("vcf_token")
        
        if not vcf_url or not current_token:
            _LOGGER.warning("Cannot download bundle: Missing URL or token")
            return
        
        try:
            session = async_get_clientsession(self.hass)
            
            # Hole verfügbare Bundles
            bundles = []
            if self.coordinator.data and "bundle_data" in self.coordinator.data:
                bundles = self.coordinator.data["bundle_data"].get("elements", [])
            
            if not bundles:
                _LOGGER.warning("No bundles available to download")
                return
            
            # Wenn kein spezifisches Bundle-ID angegeben wurde, nimm das erste
            bundle = None
            if self._bundle_id:
                for b in bundles:
                    if b.get("id") == self._bundle_id:
                        bundle = b
                        break
            else:
                bundle = bundles[0]  # Nimm das erste Bundle
            
            if not bundle:
                _LOGGER.warning(f"Bundle nicht gefunden")
                return
            
            bundle_id = bundle.get("id")
            _LOGGER.info(f"Starting download of bundle {bundle.get('name')} (ID: {bundle_id})")
            
            # Download-Anfrage starten
            download_url = f"{vcf_url}/v1/bundles/{bundle_id}"
            patch_data = {
                "operation": "DOWNLOAD"
            }
            
            headers = {
                "Authorization": f"Bearer {current_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with session.patch(download_url, headers=headers, json=patch_data, ssl=False) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Token expired, please refresh token and try again")
                elif resp.status != 202 and resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Failed to start bundle download: {resp.status} {error_text}")
                else:
                    response_data = await resp.json()
                    _LOGGER.info(f"Bundle download initiated successfully: {response_data}")
            
            # Aktualisieren des Coordinators
            await self.coordinator.async_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Error downloading VCF bundle: {e}")


class VCFDomainUpgradeButton(ButtonEntity):
    """Button to trigger VCF upgrade for a specific domain."""
    
    def __init__(self, hass, entry, coordinator, domain_id, domain_name, domain_prefix=None):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain{domain_id[:8]}"
        
        # Entity naming with space
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} Upgrade"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_name}_upgrade"
        self._attr_icon = "mdi:rocket-launch"
        
        # Store orchestrator instance
        self._orchestrator = None
    
    async def async_press(self) -> None:
        """Handle button press to start upgrade process."""
        try:
            _LOGGER.info(f"Upgrade button pressed for domain: {self._domain_name}")
            
            # Check if there's an update available
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self._domain_id, {})
            update_status = domain_data.get("update_status")
            
            if update_status != "updates_available":
                _LOGGER.warning(f"No updates available for domain {self._domain_name} (status: {update_status})")
                # Show persistent notification
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": f"No VCF updates are currently available for domain '{self._domain_name}'.",
                        "title": f"VCF Upgrade - {self._domain_name}",
                        "notification_id": f"vcf_upgrade_{self._domain_id}_no_updates"
                    }
                )
                return
            
            # Get VCF URL from entry
            vcf_url = self.entry.data.get("vcf_url")
            if not vcf_url:
                _LOGGER.error("No VCF URL configured")
                return
            
            # Create and start orchestrator
            from .upgrade_orchestrator import VCFUpgradeOrchestrator
            self._orchestrator = VCFUpgradeOrchestrator(
                self.hass, self._domain_id, self._domain_name, 
                vcf_url, self.coordinator, self._domain_prefix
            )
            
            # Store orchestrator in hass data for access by other entities
            self.hass.data.setdefault("datacenter_assistant", {})
            self.hass.data["datacenter_assistant"].setdefault("orchestrators", {})
            self.hass.data["datacenter_assistant"]["orchestrators"][self._domain_id] = self._orchestrator
            
            # Show notification that upgrade is starting
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": f"VCF upgrade process has been initiated for domain '{self._domain_name}'. "
                              f"Monitor the progress using the Update Status and Update Logs sensors.",
                    "title": f"VCF Upgrade Started - {self._domain_name}",
                    "notification_id": f"vcf_upgrade_{self._domain_id}_started"
                }
            )
            
            # Start upgrade process in background
            self.hass.async_create_task(self._orchestrator.start_upgrade_process())
            
            # Trigger coordinator refresh to update status
            await self.coordinator.async_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Error starting upgrade for domain {self._domain_name}: {e}")
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": f"Failed to start VCF upgrade for domain '{self._domain_name}': {str(e)}",
                    "title": f"VCF Upgrade Error - {self._domain_name}",
                    "notification_id": f"vcf_upgrade_{self._domain_id}_error"
                }
            )
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "domain": self._domain_name,
            "domain_id": self._domain_id,
            "purpose": "Trigger VCF upgrade process"
        }


class VCFDomainAcknowledgeAlertsButton(ButtonEntity):
    """Button to acknowledge alerts during VCF upgrade for a specific domain."""
    
    def __init__(self, hass, entry, coordinator, domain_id, domain_name, domain_prefix=None):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._domain_id = domain_id
        self._domain_name = domain_name
        self._domain_prefix = domain_prefix or f"domain{domain_id[:8]}"
        
        # Entity naming with space
        safe_name = domain_name.lower().replace(' ', '_').replace('-', '_')
        self._attr_name = f"VCF {self._domain_prefix} Acknowledge Alerts"
        self._attr_unique_id = f"vcf_{self._domain_prefix}_{safe_name}_acknowledge_alerts"
        self._attr_icon = "mdi:alert-check"
    
    async def async_press(self) -> None:
        """Handle button press to acknowledge alerts and continue upgrade."""
        try:
            _LOGGER.info(f"Acknowledge alerts button pressed for domain: {self._domain_name}")
            
            # Get orchestrator from hass data
            orchestrators = self.hass.data.get("datacenter_assistant", {}).get("orchestrators", {})
            orchestrator = orchestrators.get(self._domain_id)
            
            if not orchestrator:
                _LOGGER.warning(f"No active upgrade process found for domain {self._domain_name}")
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": f"No active upgrade process found for domain '{self._domain_name}'. "
                                  f"Please start an upgrade first.",
                        "title": f"VCF Acknowledge Alerts - {self._domain_name}",
                        "notification_id": f"vcf_acknowledge_{self._domain_id}_no_process"
                    }
                )
                return
            
            # Check if orchestrator is in the right state
            if orchestrator.current_status != "waiting_for_alert_acknowledgement":
                _LOGGER.warning(f"Domain {self._domain_name} is not waiting for alert acknowledgment (status: {orchestrator.current_status})")
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "message": f"Domain '{self._domain_name}' is not currently waiting for alert acknowledgment. "
                                  f"Current status: {orchestrator.current_status}",
                        "title": f"VCF Acknowledge Alerts - {self._domain_name}",
                        "notification_id": f"vcf_acknowledge_{self._domain_id}_wrong_state"
                    }
                )
                return
            
            # Show notification that alerts are acknowledged
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": f"Alerts have been acknowledged for domain '{self._domain_name}'. "
                              f"The upgrade process will continue.",
                    "title": f"VCF Alerts Acknowledged - {self._domain_name}",
                    "notification_id": f"vcf_acknowledge_{self._domain_id}_acknowledged"
                }
            )
            
            # Continue upgrade process
            self.hass.async_create_task(orchestrator.acknowledge_alerts())
            
            # Trigger coordinator refresh to update status
            await self.coordinator.async_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Error acknowledging alerts for domain {self._domain_name}: {e}")
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": f"Failed to acknowledge alerts for domain '{self._domain_name}': {str(e)}",
                    "title": f"VCF Acknowledge Error - {self._domain_name}",
                    "notification_id": f"vcf_acknowledge_{self._domain_id}_error"
                }
            )
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "domain": self._domain_name,
            "domain_id": self._domain_id,
            "purpose": "Acknowledge alerts and continue upgrade"
        }