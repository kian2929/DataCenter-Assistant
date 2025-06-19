import asyncio
import aiohttp
import logging
import time
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

_DOMAIN = "datacenter_assistant"

def truncate_description(text, max_length=61):
    """Truncate description text to max_length characters + '...' if needed."""
    if not text or not isinstance(text, str):
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

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
            
            # Extract active domains with prefixed variables
            active_domains = []
            domain_counter = 1
            domain_elements = domains_data.get("elements", [])
            
            for domain in domain_elements:
                if domain.get("status") == "ACTIVE":
                    domain_info = {
                        "id": domain.get("id"),
                        "name": domain.get("name"),
                        "status": domain.get("status"),
                        "prefix": f"domain{domain_counter}"
                    }
                    active_domains.append(domain_info)
                    _LOGGER.debug(f"Found active domain{domain_counter}_: {domain.get('name')} ({domain.get('id')})")
                    domain_counter += 1
            
            if not active_domains:
                _LOGGER.warning("No active domains found - failing setup")
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
                        _LOGGER.debug(f"Mapped SDDC Manager {sddc.get('fqdn')} to domain {domain['name']}")
                        break
            
            # Step 3: For each domain, check for updates using future-releases API
            _LOGGER.debug("Step 3: Checking for updates per domain using future-releases API")
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
                    
                    if not current_version:
                        _LOGGER.warning(f"Could not determine current VCF version for domain {domain_name}")
                        domain_updates[domain_id] = {
                            "domain_name": domain_name,
                            "domain_prefix": prefix,
                            "current_version": None,
                            "update_status": "error",
                            "error": "Could not determine current VCF version",
                            "next_release": None
                        }
                        continue
                    
                    # Get future releases for this domain
                    _LOGGER.debug(f"Getting future releases for domain {domain_name}")
                    future_releases_url = f"{vcf_url}/v1/releases/domains/{domain_id}/future-releases"
                    
                    async with session.get(future_releases_url, headers=headers, ssl=False) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(f"Failed to get future releases for domain {domain_name}: {resp.status}")
                            # If no future releases available, domain is up to date
                            domain_updates[domain_id] = {
                                "domain_name": domain_name,
                                "domain_prefix": prefix,
                                "current_version": current_version,
                                "update_status": "up_to_date",
                                "next_release": None
                            }
                            continue
                        future_releases_data = await resp.json()
                    
                    # Filter and find the appropriate next release
                    next_release_info = None
                    applicable_releases = []
                    
                    future_releases = future_releases_data.get("elements", [])
                    _LOGGER.debug(f"Found {len(future_releases)} future releases for domain {domain_name}")
                    
                    # Filter releases based on criteria
                    for release in future_releases:
                        # Check if release meets criteria:
                        # 1. applicabilityStatus == "APPLICABLE" 
                        # 2. isApplicable == true
                        # 3. release["version"] > current_version >= release["minCompatibleVcfVersion"]
                        
                        applicability_status = release.get("applicabilityStatus")
                        is_applicable = release.get("isApplicable", False)
                        release_version = release.get("version")
                        min_compatible_version = release.get("minCompatibleVcfVersion")
                        
                        _LOGGER.debug(f"Evaluating release {release_version}: "
                                    f"status={applicability_status}, "
                                    f"applicable={is_applicable}, "
                                    f"minCompatible={min_compatible_version}")
                        
                        if (applicability_status == "APPLICABLE" and 
                            is_applicable and 
                            release_version and 
                            min_compatible_version):
                            
                            # Compare versions (assuming they are in format x.y.z.w)
                            try:
                                def version_tuple(v):
                                    parts = v.split('.')
                                    # Normalize to 4 parts
                                    while len(parts) < 4:
                                        parts.append('0')
                                    return tuple(map(int, parts[:4]))
                                
                                current_tuple = version_tuple(current_version)
                                release_tuple = version_tuple(release_version)
                                min_compatible_tuple = version_tuple(min_compatible_version)
                                
                                # Check if: release_version > current_version >= min_compatible_version
                                if release_tuple > current_tuple >= min_compatible_tuple:
                                    applicable_releases.append(release)
                                    _LOGGER.debug(f"Release {release_version} is applicable for domain {domain_name}")
                                else:
                                    _LOGGER.debug(f"Release {release_version} does not meet version criteria: "
                                                f"{release_version} > {current_version} >= {min_compatible_version}")
                                
                            except Exception as ve:
                                _LOGGER.warning(f"Error comparing versions for release {release_version}: {ve}")
                                continue
                        else:
                            _LOGGER.debug(f"Release {release_version} does not meet applicability criteria")
                    
                    # If multiple applicable releases exist, select the oldest one (lowest version)
                    if applicable_releases:
                        _LOGGER.debug(f"Found {len(applicable_releases)} applicable releases for domain {domain_name}")
                        
                        # Sort by version to get the oldest (lowest version number)
                        def version_tuple_for_sort(v):
                            parts = v.split('.')
                            while len(parts) < 4:
                                parts.append('0')
                            try:
                                return tuple(map(int, parts[:4]))
                            except ValueError:
                                # Handle non-numeric version parts
                                _LOGGER.warning(f"Non-numeric version part in {v}, using string comparison")
                                return tuple(parts[:4])
                        
                        applicable_releases.sort(key=lambda x: version_tuple_for_sort(x.get("version", "0.0.0.0")))
                        selected_release = applicable_releases[0]
                        
                        # Capture the whole JSON as domainX_nextRelease
                        next_release_info = selected_release
                        
                        _LOGGER.info(f"Selected next release for domain {domain_name}: {selected_release.get('version')} "
                                   f"(release date: {selected_release.get('releaseDate')})")
                    else:
                        _LOGGER.debug(f"No applicable releases found for domain {domain_name}")
                    
                    # Determine final update status
                    update_status = "updates_available" if next_release_info else "up_to_date"
                    
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
                        "current_version": current_version,
                        "update_status": update_status,
                        "next_release": next_release_info  # Store the complete JSON response
                    }
                    
                    _LOGGER.info(f"Domain {domain_name} update status: {update_status}")
                    if next_release_info:
                        _LOGGER.info(f"Next VCF version available: {next_release_info.get('version')}")
                    
                except Exception as e:
                    _LOGGER.error(f"Error checking updates for domain {domain_name}: {e}")
                    domain_updates[domain_id] = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
                        "current_version": current_version if 'current_version' in locals() else None,
                        "update_status": "error",
                        "error": str(e),
                        "next_release": None
                    }
            
            return {
                "domains": active_domains,
                "domain_updates": domain_updates
            }
            
        except Exception as e:
            _LOGGER.error(f"Error in VCF update check workflow: {e}")
            return {"domains": [], "domain_updates": {}, "error": str(e)}

    async def async_fetch_resources():
        """Fetch VCF domain resource information including capacity, clusters, and hosts."""
        _LOGGER.info("VCF Resource Coordinator refreshing resource data - Starting (polling every 10s)...")
        
        # Check if VCF is configured
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"domains": [], "domain_resources": {}}

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
            _LOGGER.debug("VCF Resource Coordinator: Step 1 - Getting domains (only ACTIVE)")
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
            
            # Extract active domains with prefixed variables
            active_domains = []
            domain_counter = 1
            domain_elements = domains_data.get("elements", [])
            
            for domain in domain_elements:
                if domain.get("status") == "ACTIVE":
                    domain_info = {
                        "id": domain.get("id"),
                        "name": domain.get("name"),
                        "status": domain.get("status"),
                        "prefix": f"domain{domain_counter}"
                    }
                    active_domains.append(domain_info)
                    _LOGGER.debug(f"Found active domain{domain_counter}_: {domain.get('name')} ({domain.get('id')})")
                    domain_counter += 1
            
            if not active_domains:
                _LOGGER.warning("No active domains found - failing setup")
                return {"domains": [], "domain_resources": {}, "setup_failed": True}
            
            # Step 2: For each domain, get detailed resource information
            _LOGGER.debug("Step 2: Getting resource information for each domain")
            domain_resources = {}
            
            for domain in active_domains:
                domain_id = domain["id"]
                domain_name = domain["name"]
                prefix = domain["prefix"]
                
                try:
                    # Get domain details with capacity information
                    _LOGGER.debug(f"Getting domain details for {domain_name}")
                    domain_details_url = f"{vcf_url}/v1/domains/{domain_id}"
                    
                    async with session.get(domain_details_url, headers=headers, ssl=False) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(f"Failed to get domain details for {domain_name}: {resp.status}")
                            continue
                        domain_details = await resp.json()
                    
                    # Extract capacity information
                    capacity = domain_details.get("capacity", {})
                    clusters_info = domain_details.get("clusters", [])
                    
                    # Initialize domain resource data
                    domain_resource_data = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
                        "capacity": capacity,
                        "clusters": []
                    }
                    
                    # Step 3: For each cluster, get cluster details and host information
                    for cluster_ref in clusters_info:
                        cluster_id = cluster_ref.get("id")
                        if not cluster_id:
                            continue
                            
                        try:
                            # Get cluster details
                            _LOGGER.debug(f"Getting cluster details for cluster {cluster_id}")
                            cluster_details_url = f"{vcf_url}/v1/clusters/{cluster_id}"
                            
                            async with session.get(cluster_details_url, headers=headers, ssl=False) as resp:
                                if resp.status != 200:
                                    _LOGGER.warning(f"Failed to get cluster details for {cluster_id}: {resp.status}")
                                    continue
                                cluster_details = await resp.json()
                            
                            cluster_name = cluster_details.get("name", "Unknown")
                            hosts_info = cluster_details.get("hosts", [])
                            
                            cluster_data = {
                                "id": cluster_id,
                                "name": cluster_name,
                                "host_count": len(hosts_info),
                                "hosts": []
                            }
                            
                            # Step 4: For each host, get host details
                            for host_ref in hosts_info:
                                host_id = host_ref.get("id")
                                if not host_id:
                                    continue
                                    
                                try:
                                    # Get host details
                                    _LOGGER.debug(f"Getting host details for host {host_id}")
                                    host_details_url = f"{vcf_url}/v1/hosts/{host_id}"
                                    
                                    async with session.get(host_details_url, headers=headers, ssl=False) as resp:
                                        if resp.status != 200:
                                            _LOGGER.warning(f"Failed to get host details for {host_id}: {resp.status}")
                                            continue
                                        host_details = await resp.json()
                                    
                                    # Extract hostname from FQDN
                                    fqdn = host_details.get("fqdn", "")
                                    hostname = fqdn.split(".")[0] if fqdn else "Unknown"
                                    
                                    # Extract resource information
                                    cpu_info = host_details.get("cpu", {})
                                    memory_info = host_details.get("memory", {})
                                    storage_info = host_details.get("storage", {})
                                    
                                    host_data = {
                                        "id": host_id,
                                        "fqdn": fqdn,
                                        "hostname": hostname,
                                        "cpu": {
                                            "used_mhz": cpu_info.get("usedFrequencyMHz", 0),
                                            "total_mhz": cpu_info.get("frequencyMHz", 0),
                                            "cores": cpu_info.get("cores", 0)
                                        },
                                        "memory": {
                                            "used_mb": memory_info.get("usedCapacityMB", 0),
                                            "total_mb": memory_info.get("totalCapacityMB", 0)
                                        },
                                        "storage": {
                                            "used_mb": storage_info.get("usedCapacityMB", 0),
                                            "total_mb": storage_info.get("totalCapacityMB", 0)
                                        }
                                    }
                                    
                                    cluster_data["hosts"].append(host_data)
                                    
                                except Exception as e:
                                    _LOGGER.error(f"Error getting host details for {host_id}: {e}")
                                    continue
                            
                            domain_resource_data["clusters"].append(cluster_data)
                            
                        except Exception as e:
                            _LOGGER.error(f"Error getting cluster details for {cluster_id}: {e}")
                            continue
                    
                    domain_resources[domain_id] = domain_resource_data
                    _LOGGER.info(f"Completed resource collection for domain {domain_name}")
                    
                except Exception as e:
                    _LOGGER.error(f"Error getting resource information for domain {domain_name}: {e}")
                    domain_resources[domain_id] = {
                        "domain_name": domain_name,
                        "domain_prefix": prefix,
                        "error": str(e),
                        "capacity": {},
                        "clusters": []
                    }
            
            _LOGGER.info(f"VCF Resource Coordinator: Completed processing {len(active_domains)} domains with {len(domain_resources)} resource collections")
            
            return {
                "domains": active_domains,
                "domain_resources": domain_resources
            }
            
        except Exception as e:
            _LOGGER.error(f"Error in VCF resource collection workflow: {e}")
            return {"domains": [], "domain_resources": {}, "error": str(e)}

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
    
    # Create a new coordinator for resource monitoring
    resource_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Resources",
        update_method=async_fetch_resources,
        update_interval=timedelta(seconds=10),  # Update every 10 seconds as requested
    )

    # Speichere beide Coordinator global für andere Komponenten
    hass.data.setdefault(_DOMAIN, {})["coordinator"] = coordinator
    hass.data.setdefault(_DOMAIN, {})["resource_coordinator"] = resource_coordinator
    
    _LOGGER.info(f"Created VCF coordinators - Upgrades: {coordinator.name}, Resources: {resource_coordinator.name}")
    _LOGGER.info(f"Resource coordinator update interval: {resource_coordinator.update_interval}")
    
    return coordinator

def get_resource_coordinator(hass, config_entry):
    """Get the resource data update coordinator."""
    # The resource coordinator is created and stored when get_coordinator is called
    return hass.data.get(_DOMAIN, {}).get("resource_coordinator")
