import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

def get_coordinator(hass, config_entry):
    """Get the data update coordinator."""
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")
    vcf_refresh_token = config_entry.data.get("vcf_refresh_token", "")
    vcf_username = config_entry.data.get("vcf_username", "")
    vcf_password = config_entry.data.get("vcf_password", "")
    
    _LOGGER.critical(f"Initializing VCF coordinator with URL: {vcf_url}")

    async def refresh_vcf_token():
        """Erneuert den VCF API Token mit Anmeldedaten."""
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.critical("Cannot refresh VCF token: Missing credentials")
            return None
            
        try:
            session = async_get_clientsession(hass)
            login_url = f"{vcf_url}/v1/tokens"
            _LOGGER.critical(f"Attempting to get new token at: {login_url}")
            
            auth_data = {
                "username": vcf_username,
                "password": vcf_password
            }
            
            # Ausführliches Logging vor dem API-Aufruf
            _LOGGER.critical(f"Login request data: {auth_data}")
            
            async with session.post(login_url, json=auth_data, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.critical(f"VCF token refresh failed: {resp.status}, {error_text}")
                    return None
                    
                token_data = await resp.json()
                _LOGGER.critical(f"Token refresh response keys: {list(token_data.keys())}")
                
                # Verschiedene mögliche Token-Formate versuchen
                new_token = token_data.get("accessToken")
                if not new_token:
                    new_token = token_data.get("access_token")
                if not new_token and isinstance(token_data, str):
                    new_token = token_data
                
                if new_token:
                    _LOGGER.critical("Successfully refreshed VCF token")
                    
                    # Aktualisiere die Konfiguration
                    new_data = dict(config_entry.data)
                    new_data["vcf_token"] = new_token
                    hass.config_entries.async_update_entry(
                        config_entry,
                        data=new_data
                    )
                    
                    return new_token
                else:
                    _LOGGER.critical(f"Could not extract token from response: {token_data}")
                    return None
                    
        except Exception as e:
            _LOGGER.critical(f"Error refreshing VCF token: {e}")
            return None

    async def async_fetch_upgrades():
        """Fetch VCF upgrade information."""
        _LOGGER.debug("VCF Coordinator refreshing data")
        
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"upgradable_data": {"elements": []}}

        current_token = config_entry.data.get("vcf_token")
        
        # API-ABRUF
        try:
            session = async_get_clientsession(hass)
            api_url = f"{vcf_url}/v1/system/upgradables"
            
            headers = {
                "Authorization": f"Bearer {current_token}",
                "Accept": "application/json"
            }
            
            async with session.get(api_url, headers=headers, ssl=False) as resp:
                if resp.status == 401:  # Token abgelaufen
                    _LOGGER.info("VCF token expired, refreshing...")
                    
                    new_token = await refresh_vcf_token()
                    if new_token:
                        headers["Authorization"] = f"Bearer {new_token}"
                        _LOGGER.debug("Retrying with new token")
                        
                        async with session.get(api_url, headers=headers, ssl=False) as retry_resp:
                            if retry_resp.status != 200:
                                _LOGGER.error(f"VCF API retry failed: {retry_resp.status}")
                                return {"upgradable_data": {"elements": []}}
                            
                            raw_data = await retry_resp.json()
                    else:
                        _LOGGER.warning("Failed to refresh token")
                        return {"upgradable_data": {"elements": []}}
                elif resp.status != 200:
                    _LOGGER.error(f"VCF API error: {resp.status}")
                    return {"upgradable_data": {"elements": []}}
                else:
                    raw_data = await resp.json()
                    _LOGGER.debug(f"VCF API success, response type: {type(raw_data)}")
                
                # Normalisierung der Datenstruktur
                if isinstance(raw_data, list):
                    normalized_data = {"elements": raw_data}
                elif isinstance(raw_data, dict):
                    if "content" in raw_data and isinstance(raw_data["content"], list):
                        normalized_data = {"elements": raw_data["content"]}
                    elif "elements" in raw_data:
                        normalized_data = raw_data
                    elif "items" in raw_data and isinstance(raw_data["items"], list):
                        normalized_data = {"elements": raw_data["items"]}
                    else:
                        normalized_data = {"elements": []}
                else:
                    normalized_data = {"elements": []}
                
                # TESTCODE: Simuliere ein verfügbares Update (Kommentiere für Produktion aus)
                return {
                    "upgradable_data": {
                        "elements": [
                            {
                                "resource": {
                                    "fqdn": "esxi01.lab.local",
                                    "type": "ESXI"
                                },
                                "status": "AVAILABLE",
                                "description": "ESXi Update 7.0.3"
                            },
                            {
                                "resource": {
                                    "fqdn": "nsx.lab.local",
                                    "type": "NSX"
                                },
                                "status": "PENDING",
                                "description": "NSX Update 4.0.1"
                            }
                        ]
                    }
                }
                
                # Original code (auskommentieren für Tests)
                # return {"upgradable_data": normalized_data}
            
        except aiohttp.ClientError as e:
            _LOGGER.error(f"VCF connection error: {e}")
            return {"upgradable_data": {"elements": []}}
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch error: {e}")
            return {"upgradable_data": {"elements": []}}

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
