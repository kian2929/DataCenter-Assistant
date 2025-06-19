"""Utility functions for the DataCenter Assistant integration."""
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

# Icon mappings for different resource types
RESOURCE_ICONS = {
    "cpu": "mdi:cpu-64-bit",
    "memory": "mdi:memory",
    "storage": "mdi:harddisk",
    "default": "mdi:server"
}

def get_resource_icon(resource_type):
    """Get the appropriate icon for a resource type."""
    return RESOURCE_ICONS.get(resource_type, RESOURCE_ICONS["default"])

def truncate_description(text, max_length=61):
    """Truncate description text to max_length characters + '...' if needed."""
    if not text or not isinstance(text, str):
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def version_tuple(version_string):
    """Convert version string to tuple for comparison."""
    if not version_string:
        return (0, 0, 0, 0)
    
    parts = version_string.split('.')
    # Normalize to 4 parts
    while len(parts) < 4:
        parts.append('0')
    
    try:
        return tuple(map(int, parts[:4]))
    except ValueError:
        # Handle non-numeric version parts
        return tuple(parts[:4])

def safe_name_conversion(name):
    """Convert domain/host names to safe entity names."""
    return name.lower().replace(' ', '_').replace('-', '_')

async def make_vcf_api_request(session, url, headers, retry_refresh_func=None):
    """Make a VCF API request with automatic token refresh on 401."""
    async with session.get(url, headers=headers, ssl=False) as resp:
        if resp.status == 401 and retry_refresh_func:
            _LOGGER.info("Token expired, refreshing...")
            new_token = await retry_refresh_func()
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                # Retry with new token
                async with session.get(url, headers=headers, ssl=False) as retry_resp:
                    return retry_resp.status, await retry_resp.json() if retry_resp.status == 200 else None
            else:
                raise aiohttp.ClientError("Failed to refresh token")
        elif resp.status != 200:
            raise aiohttp.ClientError(f"API request failed: {resp.status}")
        else:
            return resp.status, await resp.json()

def create_base_entity_attributes(domain_id, domain_name, domain_prefix):
    """Create base attributes for all VCF entities."""
    return {
        "domain_id": domain_id,
        "domain_name": domain_name, 
        "domain_prefix": domain_prefix
    }
