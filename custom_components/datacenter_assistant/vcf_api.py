"""VCF API Client and Data Models for the DataCenter Assistant integration."""
import aiohttp
import logging
import time
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .utils import version_tuple

_LOGGER = logging.getLogger(__name__)


class VCFAPIClient:
    """Centralized VCF API client to handle all VCF operations."""
    
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.vcf_url = config_entry.data.get("vcf_url")
        self.vcf_username = config_entry.data.get("vcf_username", "")
        self.vcf_password = config_entry.data.get("vcf_password", "")
    
    async def get_session_with_headers(self):
        """Get session with current authentication headers."""
        current_token = self.config_entry.data.get("vcf_token")
        current_expiry = self.config_entry.data.get("token_expiry", 0)
        
        # Check if token expires in less than 10 minutes
        if current_expiry > 0 and time.time() > current_expiry - 600:
            _LOGGER.info("VCF token will expire soon, refreshing proactively")
            current_token = await self.refresh_token()
        
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {current_token}",
            "Accept": "application/json"
        }
        return session, headers
    
    async def refresh_token(self):
        """Refresh VCF API token."""
        if not self.vcf_url or not self.vcf_username or not self.vcf_password:
            _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
            return None
            
        try:
            session = async_get_clientsession(self.hass)
            login_url = f"{self.vcf_url}/v1/tokens"
            
            auth_data = {
                "username": self.vcf_username,
                "password": self.vcf_password
            }
            
            async with session.post(login_url, json=auth_data, ssl=False) as resp:
                if resp.status != 200:
                    _LOGGER.error(f"VCF token refresh failed: {resp.status}")
                    return None
                    
                token_data = await resp.json()
                new_token = token_data.get("accessToken") or token_data.get("access_token")
                
                if new_token:
                    # Update the configuration with new token and expiry time
                    new_data = dict(self.config_entry.data)
                    new_data["vcf_token"] = new_token
                    
                    expiry = int(time.time()) + 3600  # 1 hour in seconds
                    new_data["token_expiry"] = expiry
                    _LOGGER.info(f"New token will expire at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry))}")
                    
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, 
                        data=new_data
                    )
                    return new_token
                else:
                    _LOGGER.warning("Could not extract token from response")
                    return None
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")
            return None
    
    async def api_request(self, endpoint, method="GET", data=None, params=None):
        """Make a VCF API request with automatic token handling."""
        if not self.vcf_url:
            raise ValueError("VCF URL not configured")
        
        session, headers = await self.get_session_with_headers()
        url = f"{self.vcf_url}{endpoint}"
        
        async with getattr(session, method.lower())(
            url, headers=headers, json=data, params=params, ssl=False
        ) as resp:
            if resp.status == 401:
                # Try refreshing token once
                _LOGGER.info("Token expired, refreshing...")
                new_token = await self.refresh_token()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    async with getattr(session, method.lower())(
                        url, headers=headers, json=data, params=params, ssl=False
                    ) as retry_resp:
                        if retry_resp.status != 200:
                            raise aiohttp.ClientError(f"API request failed: {retry_resp.status}")
                        return await retry_resp.json()
                else:
                    raise aiohttp.ClientError("Failed to refresh token")
            elif resp.status != 200:
                raise aiohttp.ClientError(f"API request failed: {resp.status}")
            else:
                return await resp.json()


class VCFDomain:
    """Data model for VCF Domain with business logic."""
    
    def __init__(self, domain_data, domain_counter=1):
        self.id = domain_data.get("id")
        self.name = domain_data.get("name")
        self.status = domain_data.get("status")
        self.prefix = f"domain{domain_counter}"
        self.sddc_manager_id = None
        self.sddc_manager_fqdn = None
        self.current_version = None
        self.update_status = "unknown"
        self.next_release = None
    
    def set_sddc_manager(self, sddc_id, sddc_fqdn):
        """Set SDDC manager information."""
        self.sddc_manager_id = sddc_id
        self.sddc_manager_fqdn = sddc_fqdn
    
    def set_update_info(self, current_version, update_status, next_release=None):
        """Set update information."""
        self.current_version = current_version
        self.update_status = update_status
        self.next_release = next_release
    
    def find_applicable_releases(self, future_releases):
        """Find applicable releases for this domain."""
        if not self.current_version:
            _LOGGER.warning(f"Domain {self.name}: No current version set, cannot find applicable releases")
            return []
        
        _LOGGER.debug(f"Domain {self.name}: Finding applicable releases from {len(future_releases)} future releases")
        applicable_releases = []
        
        for release in future_releases:
            applicability_status = release.get("applicabilityStatus")
            is_applicable = release.get("isApplicable", False)
            release_version = release.get("version")
            min_compatible_version = release.get("minCompatibleVcfVersion")
            
            _LOGGER.debug(f"Domain {self.name}: Evaluating release {release_version}: "
                        f"status={applicability_status}, applicable={is_applicable}, "
                        f"minCompatible={min_compatible_version}")
            
            if (applicability_status == "APPLICABLE" and 
                is_applicable and 
                release_version and 
                min_compatible_version):
                
                try:
                    current_tuple = version_tuple(self.current_version)
                    release_tuple = version_tuple(release_version)
                    min_compatible_tuple = version_tuple(min_compatible_version)
                    
                    if release_tuple > current_tuple >= min_compatible_tuple:
                        applicable_releases.append(release)
                        _LOGGER.debug(f"Domain {self.name}: Release {release_version} is applicable")
                    else:
                        _LOGGER.debug(f"Domain {self.name}: Release {release_version} does not meet version criteria: "
                                    f"{release_version} > {self.current_version} >= {min_compatible_version}")
                
                except Exception as ve:
                    _LOGGER.warning(f"Domain {self.name}: Error comparing versions for release {release_version}: {ve}")
                    continue
            else:
                _LOGGER.debug(f"Domain {self.name}: Release {release_version} does not meet applicability criteria")
        
        _LOGGER.info(f"Domain {self.name}: Found {len(applicable_releases)} applicable releases")
        return applicable_releases
    
    def to_dict(self):
        """Convert to dictionary for coordinator data."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "prefix": self.prefix,
            "sddc_manager_id": self.sddc_manager_id,
            "sddc_manager_fqdn": self.sddc_manager_fqdn
        }
    
    def update_dict(self):
        """Convert to dictionary for domain updates."""
        return {
            "domain_name": self.name,
            "domain_prefix": self.prefix,
            "current_version": self.current_version,
            "update_status": self.update_status,
            "next_release": self.next_release
        }
