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
        """Fetch VCF domain and update information following the proper workflow from flow.txt."""
        _LOGGER.debug("VCF Coordinator refreshing domain and update data - following workflow")
        
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
            # Step 1: Get Domain Information - only consider ACTIVE domains
            _LOGGER.debug("Step 1: Getting domains (only ACTIVE)")
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
            
            # Extract active domains with prefixed variables as per flow.txt
            active_domains = []
            domain_counter = 1
            domain_elements = domains_data.get("elements", [])
            
            for domain in domain_elements:
                if domain.get("status") == "ACTIVE":
                    domain_info = {
                        "id": domain.get("id"),
                        "name": domain.get("name"),
                        "status": domain.get("status"),
                        "prefix": f"domain{domain_counter}_"
                    }
                    active_domains.append(domain_info)
                    _LOGGER.debug(f"Found active domain{domain_counter}_: {domain.get('name')} ({domain.get('id')})")
                    domain_counter += 1
            
            if not active_domains:
                _LOGGER.warning("No active domains found - failing setup as per flow.txt")
                return {"domains": [], "domain_updates": {}, "setup_failed": True}
            
            # Step 2: Get SDDC Manager Information
            _LOGGER.debug("Step 2: Getting SDDC managers to match with domains")
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
                        domain["sddc_manager_version"] = sddc.get("version")
                        _LOGGER.debug(f"Mapped SDDC Manager {sddc.get('fqdn')} to domain {domain['name']}")
                        break
            
            # Step 3: For each domain, follow the update checking workflow
            _LOGGER.debug("Step 3: Checking for updates per domain following flow.txt workflow")
            domain_updates = {}
            
            for domain in active_domains:
                domain_id = domain["id"]
                domain_name = domain["name"]
                prefix = domain["prefix"]
                
                try:
                    # Get current VCF version for this domain
                    _LOGGER.debug(f"Getting current VCF version for domain {domain_name}")
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
                    
                    # Get bundles to find VCF updates (as per flow.txt)
                    _LOGGER.debug(f"Getting bundles for VCF updates for domain {domain_name}")
                    bundles_url = f"{vcf_url}/v1/bundles"
                    
                    async with session.get(bundles_url, headers=headers, ssl=False) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(f"Failed to get bundles for domain {domain_name}: {resp.status}")
                            continue
                        bundles_data = await resp.json()
                    
                    # Filter bundles with "VMware Cloud Foundation (version)" in description
                    vcf_bundles = []
                    bundles_elements = bundles_data.get("elements", [])
                    
                    import re
                    for bundle in bundles_elements:
                        description = bundle.get("description", "")
                        # Look for "VMware Cloud Foundation" pattern as per flow.txt
                        if re.search(r"VMware Cloud Foundation.*\(\d+\.\d+(?:\.\d+)?\)", description, re.IGNORECASE):
                            vcf_bundles.append(bundle)
                    
                    # Initialize next version info
                    next_version_info = None
                    
                    if not vcf_bundles:
                        # No VCF bundles found - report "up to date" as per flow.txt
                        _LOGGER.debug(f"No VCF update bundles found for domain {domain_name} - reporting up to date")
                        domain_updates[domain_id] = {
                            "domain_name": domain_name,
                            "domain_prefix": prefix,
                            "current_version": current_version,
                            "update_status": "up_to_date",
                            "next_version": None,
                            "component_updates": {}
                        }
                        continue
                    
                    # Find the oldest bundle by releaseDate as per flow.txt
                    sorted_bundles = sorted(vcf_bundles, key=lambda x: x.get("releaseDate", ""))
                    if sorted_bundles:
                        target_bundle = sorted_bundles[0]
                        
                        # Extract version info as per flow.txt variable naming
                        description = target_bundle.get("description", "")
                        version_pattern = r"VMware Cloud Foundation.*\((\d+\.\d+(?:\.\d+)?)\)"
                        match = re.search(version_pattern, description, re.IGNORECASE)
                        target_version = match.group(1) if match else "Unknown"
                        
                        next_version_info = {
                            "versionDescription": description,  # nextVersion_versionDescription
                            "versionNumber": target_version,     # nextVersion_versionNumber
                            "releaseDate": target_bundle.get("releaseDate"),  # nextVersion_releaseDate
                            "bundleId": target_bundle.get("id"),
                            "bundlesToDownload": [target_bundle.get("id")]  # nextVersion_bundlesToDownload
                        }
                        
                        # Check if SDDC_MANAGER component needs update
                        components = target_bundle.get("components", [])
                        sddc_component = None
                        for comp in components:
                            if comp.get("type") == "SDDC_MANAGER":
                                sddc_component = comp
                                break
                        
                        # Check if update is actually needed by comparing versions
                        update_needed = True
                        if sddc_component and current_version:
                            to_version = sddc_component.get("toVersion")
                            if to_version and current_version:
                                # Simple version comparison - you might want to enhance this
                                update_needed = to_version != current_version
                        
                        if not update_needed:
                            _LOGGER.debug(f"SDDC Manager version check shows no update needed for {domain_name}")
                            domain_updates[domain_id] = {
                                "domain_name": domain_name,
                                "domain_prefix": prefix,
                                "current_version": current_version,
                                "update_status": "up_to_date",
                                "next_version": None,
                                "component_updates": {}
                            }
                            continue
                    
                    # Get upgradable components for this domain with target version
                    component_updates = {}
                    if next_version_info and next_version_info["versionNumber"] != "Unknown":
                        _LOGGER.debug(f"Getting upgradables for domain {domain_name} with target version {next_version_info['versionNumber']}")
                        upgradables_url = f"{vcf_url}/v1/upgradables/domains/{domain_id}"
                        params = {"targetVersion": next_version_info["versionNumber"]}
                        
                        async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                            if resp.status == 200:
                                upgradables_data = await resp.json()
                                
                                # Get component details for each component bundle
                                for component in upgradables_data.get("elements", []):
                                    component_bundle_id = component.get("bundleId")
                                    component_type = component.get("componentType", "Unknown")
                                    
                                    if component_bundle_id:
                                        bundle_detail_url = f"{vcf_url}/v1/bundles/{component_bundle_id}"
                                        
                                        async with session.get(bundle_detail_url, headers=headers, ssl=False) as bundle_resp:
                                            if bundle_resp.status == 200:
                                                bundle_detail = await bundle_resp.json()
                                                # Store component update info as per flow.txt format
                                                component_updates[f"componentUpdate{len(component_updates)+1}"] = {
                                                    "id": component_bundle_id,
                                                    "description": bundle_detail.get("description", ""),
                                                    "version": bundle_detail.get("version", ""),
                                                    "componentType": component_type
                                                }
                            else:
                                _LOGGER.warning(f"Failed to get upgradables for domain {domain_name}: {resp.status}")
                    
                    # Determine final update status
                    update_status = "updates_available" if next_version_info else "up_to_date"
                    
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
                        "current_version": current_version,
                        "update_status": update_status,
                        "next_version": next_version_info,
                        "component_updates": component_updates
                    }
                    
                    _LOGGER.info(f"Domain {domain_name} update status: {update_status}")
                    if next_version_info:
                        _LOGGER.info(f"Next VCF version available: {next_version_info['versionNumber']}")
                    
                except Exception as e:
                    _LOGGER.error(f"Error checking updates for domain {domain_name}: {e}")
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
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
