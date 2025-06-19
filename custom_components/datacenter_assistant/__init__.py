import logging
import asyncio
import time
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = "datacenter_assistant"
PLATFORMS = ["sensor", "binary_sensor", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DataCenter Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry

    # Configure logging
    logging.getLogger('custom_components.datacenter_assistant').setLevel(logging.CRITICAL)
    
    _LOGGER.debug("DataCenter Assistant integration loaded")
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await _async_setup_services(hass, entry)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(await asyncio.gather(*[
        hass.config_entries.async_forward_entry_unload(entry, platform)
        for platform in PLATFORMS
    ]))

    if unload_ok:
        # Remove services
        for service in ["refresh_token", "trigger_upgrade", "download_bundle"]:
            hass.services.async_remove(DOMAIN, service)
        
        # Clean up data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_setup(hass: HomeAssistant, config):
    """Set up the component (optional)."""
    return True


async def _refresh_vcf_token(hass: HomeAssistant, entry: ConfigEntry):
    """Common token refresh logic."""
    vcf_url = entry.data.get("vcf_url")
    vcf_username = entry.data.get("vcf_username", "")
    vcf_password = entry.data.get("vcf_password", "")
    
    if not all([vcf_url, vcf_username, vcf_password]):
        _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
        return None
        
    try:
        session = async_get_clientsession(hass)
        auth_data = {"username": vcf_username, "password": vcf_password}
        
        async with session.post(f"{vcf_url}/v1/tokens", json=auth_data, ssl=False) as resp:
            if resp.status != 200:
                _LOGGER.error(f"VCF token refresh failed: {resp.status}")
                return None
                
            token_data = await resp.json()
            new_token = token_data.get("accessToken") or token_data.get("access_token")
            
            if new_token:
                new_data = dict(entry.data)
                new_data.update({
                    "vcf_token": new_token,
                    "token_expiry": int(time.time()) + 3600
                })
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info("VCF token refreshed successfully")
                return new_token
            else:
                _LOGGER.warning("Could not extract token from response")
                return None
                
    except Exception as e:
        _LOGGER.error(f"Error refreshing VCF token: {e}")
        return None


async def _make_vcf_api_call(hass: HomeAssistant, entry: ConfigEntry, method: str, endpoint: str, data=None):
    """Common VCF API call with error handling."""
    vcf_url = entry.data.get("vcf_url")
    current_token = entry.data.get("vcf_token")
    
    if not vcf_url or not current_token:
        _LOGGER.warning("Cannot make API call: Missing URL or token")
        return None, None
    
    session = async_get_clientsession(hass)
    headers = {
        "Authorization": f"Bearer {current_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    url = f"{vcf_url}{endpoint}"
    
    try:
        async with session.request(method, url, headers=headers, json=data or {}, ssl=False) as resp:
            if resp.status == 401:
                _LOGGER.warning("Token expired, please refresh token")
            elif resp.status not in [200, 202]:
                error_text = await resp.text()
                _LOGGER.error(f"API call failed: {resp.status} {error_text}")
            return resp.status, resp
    except Exception as e:
        _LOGGER.error(f"Error making API call: {e}")
        return None, None


async def _async_setup_services(hass: HomeAssistant, entry: ConfigEntry):
    """Set up services for VCF integration."""
    async def refresh_token_service(call: ServiceCall):
        """Service to refresh VCF token."""
        _LOGGER.info("Service: Refreshing VCF token")
        await _refresh_vcf_token(hass, entry)
    
    async def trigger_upgrade_service(call: ServiceCall):
        """Service to trigger VCF upgrade."""
        _LOGGER.info("Service: Triggering VCF upgrade")
        
        component_type = call.data.get("component_type")
        fqdn = call.data.get("fqdn")
        
        if not component_type or not fqdn:
            _LOGGER.error("Component type and FQDN are required for upgrade")
            return
            
        endpoint = f"/v1/system/updates/{component_type.lower()}/{fqdn}/start"
        status, resp = await _make_vcf_api_call(hass, entry, "POST", endpoint)
        
        if status in [200, 202]:
            _LOGGER.info(f"Successfully initiated upgrade for {component_type} {fqdn}")
    
    async def download_bundle_service(call: ServiceCall):
        """Service to download VCF bundle."""
        _LOGGER.info("Service: Downloading VCF bundle")
        
        bundle_id = call.data.get("bundle_id")
        if not bundle_id:
            _LOGGER.error("Bundle ID is required for download")
            return
            
        endpoint = f"/v1/bundles/{bundle_id}"
        status, resp = await _make_vcf_api_call(hass, entry, "PATCH", endpoint, {"operation": "DOWNLOAD"})
        
        if status in [200, 202]:
            _LOGGER.info(f"Successfully initiated bundle download: {bundle_id}")
    
    # Register services
    services = [
        ("refresh_token", refresh_token_service),
        ("trigger_upgrade", trigger_upgrade_service),
        ("download_bundle", download_bundle_service)
    ]
    
    for service_name, service_func in services:
        hass.services.async_register(DOMAIN, service_name, service_func)
