import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

def get_coordinator(hass, config_entry):
    """Get the data update coordinator."""
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")
    vcf_username = config_entry.data.get("vcf_username", "")
    vcf_password = config_entry.data.get("vcf_password", "")
    
    # Besseres Debug-Logging
    _LOGGER.debug(f"Initializing VCF coordinator with URL: {vcf_url}")
    _LOGGER.debug("TESTLOG: Komponente datacenter_assistant wurde geladen")

    # Mutable token zur Aktualisierung
    token_data = {"current_token": vcf_token}
    
    headers = {
        "Authorization": f"Bearer {token_data['current_token']}",
        "Accept": "application/json"
    }

    async def refresh_vcf_token():
        """Erneuert den VCF API Token."""
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.warning("Cannot refresh VCF token: Missing credentials")
            return None
            
        try:
            session = async_get_clientsession(hass)
            login_url = f"{vcf_url}/v1/tokens"
            _LOGGER.debug(f"Attempting to refresh VCF token at: {login_url}")
            
            auth_data = {
                "username": vcf_username,
                "password": vcf_password
            }
            
            async with session.post(login_url, json=auth_data, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"VCF token refresh failed: {resp.status}, {error_text}")
                    return None
                    
                token_data = await resp.json()
                _LOGGER.debug(f"Token refresh response: {token_data}")
                
                # Anpassen je nach tatsächlicher API-Antwort
                new_token = token_data.get("accessToken")
                if not new_token:
                    new_token = token_data.get("access_token")
                if not new_token and isinstance(token_data, str):
                    new_token = token_data
                
                if new_token:
                    _LOGGER.info("Successfully refreshed VCF token")
                    
                    # Aktualisiere die Konfiguration für Persistenz
                    new_data = dict(config_entry.data)
                    new_data["vcf_token"] = new_token
                    hass.config_entries.async_update_entry(
                        config_entry,
                        data=new_data
                    )
                    
                    return new_token
                else:
                    _LOGGER.error(f"Could not extract token from response: {token_data}")
                    return None
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing VCF token: {e}")
            return None

    async def async_fetch_upgrades():
        """Fetch VCF upgrade information with detailed logging."""
        _LOGGER.debug("VCF Coordinator async_fetch_upgrades() is being called")
        
        # Wenn keine VCF-Konfiguration vorhanden ist
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"upgradable_data": {"elements": []}}

        # API-ABRUF
        try:
            session = async_get_clientsession(hass)
            api_url = f"{vcf_url}/v1/system/upgradables"
            _LOGGER.debug(f"Fetching VCF data from: {api_url}")
            
            # Aktualisierte Header mit aktuellem Token
            current_headers = {
                "Authorization": f"Bearer {token_data['current_token']}",
                "Accept": "application/json"
            }
            
            async with session.get(api_url, headers=current_headers, ssl=False) as resp:
                if resp.status == 401:  # Token abgelaufen
                    _LOGGER.warning("VCF token expired, attempting refresh")
                    new_token = await refresh_vcf_token()
                    if new_token:
                        token_data["current_token"] = new_token
                        current_headers["Authorization"] = f"Bearer {new_token}"
                        
                        # Erneuter Versuch mit neuem Token
                        _LOGGER.debug("Retrying with new token")
                        async with session.get(api_url, headers=current_headers, ssl=False) as retry_resp:
                            if retry_resp.status != 200:
                                error_text = await retry_resp.text()
                                _LOGGER.error(f"VCF API retry returned status {retry_resp.status}: {error_text}")
                                return {"upgradable_data": {"elements": []}}
                            
                            raw_data = await retry_resp.json()
                    else:
                        _LOGGER.error("Failed to refresh token")
                        return {"upgradable_data": {"elements": []}}
                elif resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"VCF API returned status {resp.status}: {error_text}")
                    return {"upgradable_data": {"elements": []}}
                else:
                    raw_data = await resp.json()
                
                _LOGGER.debug(f"VCF API raw response: {raw_data}")
                
                # Umfangreiches Debug-Logging
                if isinstance(raw_data, dict):
                    _LOGGER.debug(f"VCF response is dict with keys: {raw_data.keys()}")
                    for key in raw_data.keys():
                        _LOGGER.debug(f"VCF key '{key}' type: {type(raw_data[key])}")
                        if isinstance(raw_data[key], (list, dict)) and key != "elements":
                            _LOGGER.debug(f"Contents of '{key}': {raw_data[key]}")
                elif isinstance(raw_data, list):
                    _LOGGER.debug(f"VCF response is list with {len(raw_data)} items")
                    if raw_data and len(raw_data) > 0:
                        _LOGGER.debug(f"First item: {raw_data[0]}")
                else:
                    _LOGGER.debug(f"VCF response is type: {type(raw_data)}")
                
                # Normalisierung der Datenstruktur
                if isinstance(raw_data, list):
                    _LOGGER.debug("Converting list response to elements dict")
                    normalized_data = {"elements": raw_data}
                elif isinstance(raw_data, dict):
                    if "content" in raw_data and isinstance(raw_data["content"], list):
                        _LOGGER.debug("Found content list in response")
                        normalized_data = {"elements": raw_data["content"]}
                    elif "elements" in raw_data:
                        _LOGGER.debug("Using existing elements in response")
                        normalized_data = raw_data
                    elif "items" in raw_data and isinstance(raw_data["items"], list):
                        _LOGGER.debug("Found items list in response")
                        normalized_data = {"elements": raw_data["items"]}
                    else:
                        _LOGGER.warning(f"Unknown VCF API response structure")
                        normalized_data = {"elements": []}
                else:
                    _LOGGER.warning(f"Unexpected VCF API response type: {type(raw_data)}")
                    normalized_data = {"elements": []}
                
                _LOGGER.debug(f"Normalized VCF data: {normalized_data}")
                return {"upgradable_data": normalized_data}
                
        except aiohttp.ClientError as e:
            _LOGGER.error(f"VCF connection error: {e}")
            return {"upgradable_data": {"elements": []}}
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch failed: {e}")
            _LOGGER.exception("Detailed exception")  # Detaillierte Exception für besseres Debugging
            return {"upgradable_data": {"elements": []}}

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
