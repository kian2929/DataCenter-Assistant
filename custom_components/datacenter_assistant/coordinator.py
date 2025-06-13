import asyncio
import aiohttp
import logging
import time
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

_DOMAIN = "datacenter_assistant"

def get_coordinator(hass, config_entry):
    """Get the data update coordinator."""
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")
    vcf_refresh_token = config_entry.data.get("vcf_refresh_token", "")
    vcf_username = config_entry.data.get("vcf_username", "")
    vcf_password = config_entry.data.get("vcf_password", "")
    token_expiry = config_entry.data.get("token_expiry", 0)  # Default 0 für unbekannt
    
    _LOGGER.debug(f"Initializing VCF coordinator with URL: {vcf_url}")

    async def refresh_vcf_token():
        """Refresh VCF API token."""
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
            return None
            
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
                    return None
                    
                token_data = await resp.json()
                new_token = token_data.get("accessToken") or token_data.get("access_token")
                
                if new_token:
                    # Aktualisiere die Konfiguration mit neuem Token und Ablaufzeit
                    new_data = dict(config_entry.data)
                    new_data["vcf_token"] = new_token
                    
                    # Token-Ablaufzeit berechnen (1 Stunde ab jetzt)
                    expiry = int(time.time()) + 3600  # 1 Stunde in Sekunden
                    new_data["token_expiry"] = expiry
                    _LOGGER.info(f"New token will expire at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))}")
                    
                    hass.config_entries.async_update_entry(
                        config_entry, 
                        data=new_data
                    )
                    return new_token
                else:
                    _LOGGER.warning(f"Could not extract token from response")
                    return None
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")
            return None

    async def async_fetch_upgrades():
        """Fetch VCF domain and update information following the proper workflow."""
        _LOGGER.debug("VCF Coordinator refreshing domain and update data")
        
        # Check if VCF is configured
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"domains": [], "domain_updates": {}}

        current_token = config_entry.data.get("vcf_token")
        current_expiry = config_entry.data.get("token_expiry", 0)
        
        # Check if token expires in less than 10 minutes
        if current_expiry > 0 and time.time() > current_expiry - 600:
            _LOGGER.info("VCF token will expire soon, refreshing proactively")
            new_token = await refresh_vcf_token()
            if new_token:
                current_token = new_token
            else:
                _LOGGER.warning("Failed to refresh token proactively")
        
        session = async_get_clientsession(hass)
        headers = {
            "Authorization": f"Bearer {current_token}",
            "Accept": "application/json"
        }
        
        try:
            # Step 1: Get domains
            _LOGGER.debug("Step 1: Getting domains")
            domains_url = f"{vcf_url}/v1/domains"
            
            async with session.get(domains_url, headers=headers, ssl=False) as resp:
                if resp.status == 401:
                    _LOGGER.info("Token expired, refreshing...")
                    new_token = await refresh_vcf_token()
                    if new_token:
                        headers["Authorization"] = f"Bearer {new_token}"
                        current_token = new_token
                    else:
                        raise aiohttp.ClientError("Failed to refresh token")
                        
                    # Retry with new token
                    async with session.get(domains_url, headers=headers, ssl=False) as retry_resp:
                        if retry_resp.status != 200:
                            raise aiohttp.ClientError(f"Domains API failed: {retry_resp.status}")
                        domains_data = await retry_resp.json()
                elif resp.status != 200:
                    raise aiohttp.ClientError(f"Domains API failed: {resp.status}")
                else:
                    domains_data = await resp.json()
            
            # Extract active domains
            active_domains = []
            domain_elements = domains_data.get("elements", [])
            
            for domain in domain_elements:
                if domain.get("status") == "ACTIVE":
                    active_domains.append({
                        "id": domain.get("id"),
                        "name": domain.get("name"),
                        "status": domain.get("status")
                    })
                    _LOGGER.debug(f"Found active domain: {domain.get('name')} ({domain.get('id')})")
            
            if not active_domains:
                _LOGGER.warning("No active domains found")
                return {"domains": [], "domain_updates": {}}
            
            # Step 2: Get SDDC managers for each domain
            _LOGGER.debug("Step 2: Getting SDDC managers")
            sddc_managers_url = f"{vcf_url}/v1/sddc-managers"
            
            async with session.get(sddc_managers_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError(f"SDDC Managers API failed: {resp.status}")
                sddc_data = await resp.json()
            
            # Map SDDC managers to domains
            sddc_elements = sddc_data.get("elements", [])
            for domain in active_domains:
                for sddc in sddc_elements:
                    if sddc.get("domain", {}).get("id") == domain["id"]:
                        domain["sddc_manager_id"] = sddc.get("id")
                        domain["sddc_manager_fqdn"] = sddc.get("fqdn")
                        break
            
            # Step 3: For each domain, check for updates
            _LOGGER.debug("Step 3: Checking for updates per domain")
            domain_updates = {}
            
            for domain in active_domains:
                domain_id = domain["id"]
                domain_name = domain["name"]
                
                try:
                    # Get current VCF version for this domain
                    releases_url = f"{vcf_url}/v1/releases"
                    params = {"domainId": domain_id}
                    
                    async with session.get(releases_url, headers=headers, params=params, ssl=False) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(f"Failed to get releases for domain {domain_name}: {resp.status}")
                            continue
                        releases_data = await resp.json()
                    
                    current_version = None
                    if releases_data.get("elements"):
                        current_version = releases_data["elements"][0].get("version")
                    
                    # Get available bundles
                    bundles_url = f"{vcf_url}/v1/bundles"
                    
                    async with session.get(bundles_url, headers=headers, ssl=False) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(f"Failed to get bundles for domain {domain_name}: {resp.status}")
                            continue
                        bundles_data = await resp.json()
                    
                    # Filter bundles for VMware Cloud Foundation updates
                    vcf_bundles = []
                    bundles_elements = bundles_data.get("elements", [])
                    
                    for bundle in bundles_elements:
                        description = bundle.get("description", "")
                        if "VMware Cloud Foundation" in description:
                            vcf_bundles.append(bundle)
                    
                    # Find the latest available update
                    next_version_info = None
                    if vcf_bundles:
                        # Sort by release date, get the oldest one (as per flow.txt)
                        sorted_bundles = sorted(vcf_bundles, key=lambda x: x.get("releaseDate", ""))
                        if sorted_bundles:
                            latest_bundle = sorted_bundles[0]
                            
                            # Extract version from description
                            description = latest_bundle.get("description", "")
                            version_match = None
                            # Try to extract version number from description
                            import re
                            version_pattern = r'VMware Cloud Foundation[^\d]*(\d+\.\d+(?:\.\d+)?)'
                            match = re.search(version_pattern, description)
                            if match:
                                version_match = match.group(1)
                            
                            next_version_info = {
                                "versionDescription": description,
                                "versionNumber": version_match or "Unknown",
                                "releaseDate": latest_bundle.get("releaseDate"),
                                "bundleId": latest_bundle.get("id"),
                                "bundlesToDownload": [latest_bundle.get("id")]
                            }
                    
                    # Check upgradable components for this domain
                    component_updates = {}
                    if next_version_info and next_version_info["versionNumber"] != "Unknown":
                        upgradables_url = f"{vcf_url}/v1/upgradables/domains/{domain_id}"
                        params = {"targetVersion": next_version_info["versionNumber"]}
                        
                        async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                            if resp.status == 200:
                                upgradables_data = await resp.json()
                                
                                # Get component details
                                for component in upgradables_data.get("elements", []):
                                    component_bundle_id = component.get("bundleId")
                                    if component_bundle_id:
                                        bundle_detail_url = f"{vcf_url}/v1/bundles/{component_bundle_id}"
                                        
                                        async with session.get(bundle_detail_url, headers=headers, ssl=False) as bundle_resp:
                                            if bundle_resp.status == 200:
                                                bundle_detail = await bundle_resp.json()
                                                component_name = component.get("componentType", "Unknown")
                                                component_updates[component_name] = {
                                                    "id": component_bundle_id,
                                                    "description": bundle_detail.get("description", ""),
                                                    "version": bundle_detail.get("version", "")
                                                }
                    
                    # Determine update status
                    update_status = "up_to_date"
                    if next_version_info:
                        if current_version and next_version_info["versionNumber"] != "Unknown":
                            # Simple version comparison (you might want to improve this)
                            if next_version_info["versionNumber"] != current_version:
                                update_status = "updates_available"
                        else:
                            update_status = "updates_available"
                    
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "current_version": current_version,
                        "update_status": update_status,
                        "next_version": next_version_info,
                        "component_updates": component_updates
                    }
                    
                    _LOGGER.debug(f"Domain {domain_name} update status: {update_status}")
                    
                except Exception as e:
                    _LOGGER.error(f"Error checking updates for domain {domain_name}: {e}")
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "current_version": None,
                        "update_status": "error",
                        "error": str(e),
                        "next_version": None,
                        "component_updates": {}
                    }
            
            return {
                "domains": active_domains,
                "domain_updates": domain_updates
            }
            
        except Exception as e:
            _LOGGER.error(f"Error in VCF update check workflow: {e}")
            return {"domains": [], "domain_updates": {}, "error": str(e)}

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
    
    # Speichere den Coordinator global für andere Komponenten
    hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    
    return coordinator
