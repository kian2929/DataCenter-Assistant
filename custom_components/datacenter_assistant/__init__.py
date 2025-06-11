import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.entity_platform as platform
import time

_LOGGER = logging.getLogger(__name__)
_LOGGER.debug("Initialized with log handlers: %s", logging.getLogger().handlers)

DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    # Configure logging
    logging.getLogger('custom_components.datacenter_assistant').setLevel(logging.CRITICAL)
    
    # Log integration loading
    _LOGGER.debug("DataCenter Assistant integration loaded")    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await _async_setup_services(hass, entry)
    
    # Register services
    await _async_setup_services(hass, entry)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(*[
            hass.config_entries.async_forward_entry_unload(entry, platform)
            for platform in PLATFORMS
        ])
    )

    if unload_ok:
        # Remove services
        hass.services.async_remove(DOMAIN, "refresh_token")
        hass.services.async_remove(DOMAIN, "trigger_upgrade")
        hass.services.async_remove(DOMAIN, "download_bundle")
        
        # Clean up data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_setup(hass: HomeAssistant, config):
    """Set up the component (optional)."""
    return True


async def _async_setup_services(hass: HomeAssistant, entry: ConfigEntry):
    """Set up services for VCF integration."""
    
    async def refresh_token_service(call: ServiceCall):
        """Service to refresh VCF token."""
        _LOGGER.info("Service: Refreshing VCF token")
        
        vcf_url = entry.data.get("vcf_url")
        vcf_username = entry.data.get("vcf_username", "")
        vcf_password = entry.data.get("vcf_password", "")
        
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
            return
            
        try:
            session = async_get_clientsession(hass)
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
                    new_data = dict(entry.data)
                    new_data["vcf_token"] = new_token
                    expiry = int(time.time()) + 3600
                    new_data["token_expiry"] = expiry
                    
                    hass.config_entries.async_update_entry(entry, data=new_data)
                    _LOGGER.info("VCF token refreshed successfully")
                else:
                    _LOGGER.warning("Could not extract token from response")
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")
    
    async def trigger_upgrade_service(call: ServiceCall):
        """Service to trigger VCF upgrade."""
        _LOGGER.info("Service: Triggering VCF upgrade")
        
        component_type = call.data.get("component_type")
        fqdn = call.data.get("fqdn")
        
        if not component_type or not fqdn:
            _LOGGER.error("Component type and FQDN are required for upgrade")
            return
            
        vcf_url = entry.data.get("vcf_url")
        current_token = entry.data.get("vcf_token")
        
        if not vcf_url or not current_token:
            _LOGGER.warning("Cannot execute upgrade: Missing URL or token")
            return
        
        try:
            session = async_get_clientsession(hass)
            api_url = f"{vcf_url}/v1/system/updates/{component_type.lower()}/{fqdn}/start"
            
            headers = {
                "Authorization": f"Bearer {current_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            async with session.post(api_url, headers=headers, json={}, ssl=False) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Token expired during upgrade, please refresh token")
                elif resp.status not in [200, 202]:
                    error_text = await resp.text()
                    _LOGGER.error(f"Failed to start upgrade: {resp.status} {error_text}")
                else:
                    _LOGGER.info(f"Successfully initiated upgrade for {component_type} {fqdn}")
                    
        except Exception as e:
            _LOGGER.error(f"Error executing VCF upgrade: {e}")
    
    async def download_bundle_service(call: ServiceCall):
        """Service to download VCF bundle."""
        _LOGGER.info("Service: Downloading VCF bundle")
        
        bundle_id = call.data.get("bundle_id")
        
        if not bundle_id:
            _LOGGER.error("Bundle ID is required for download")
            return
            
        vcf_url = entry.data.get("vcf_url")
        current_token = entry.data.get("vcf_token")
        
        if not vcf_url or not current_token:
            _LOGGER.warning("Cannot download bundle: Missing URL or token")
            return
        
        try:
            session = async_get_clientsession(hass)
            download_url = f"{vcf_url}/v1/bundles/{bundle_id}"
            patch_data = {"operation": "DOWNLOAD"}
            
            headers = {
                "Authorization": f"Bearer {current_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with session.patch(download_url, headers=headers, json=patch_data, ssl=False) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Token expired during download, please refresh token")
                elif resp.status not in [200, 202]:
                    error_text = await resp.text()
                    _LOGGER.error(f"Failed to start bundle download: {resp.status} {error_text}")
                else:
                    _LOGGER.info(f"Successfully initiated bundle download: {bundle_id}")
                    
        except Exception as e:
            _LOGGER.error(f"Error downloading VCF bundle: {e}")
    
    # Register services
    hass.services.async_register(DOMAIN, "refresh_token", refresh_token_service)
    hass.services.async_register(DOMAIN, "trigger_upgrade", trigger_upgrade_service)
    hass.services.async_register(DOMAIN, "download_bundle", download_bundle_service)
