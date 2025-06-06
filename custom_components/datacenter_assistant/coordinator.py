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
        """Fetch VCF upgrade information with detailed logging."""
        _LOGGER.critical("VCF Coordinator async_fetch_upgrades() is being called")
        
        # Prüfe, ob VCF konfiguriert ist
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"upgradable_data": {"elements": []}}

        current_token = config_entry.data.get("vcf_token")
        
        # API-ABRUF
        try:
            session = async_get_clientsession(hass)
            api_url = f"{vcf_url}/v1/system/upgradables"
            _LOGGER.critical(f"Fetching VCF data from: {api_url}")
            
            # Headers für den API-Aufruf
            headers = {
                "Authorization": f"Bearer {current_token}",
                "Accept": "application/json"
            }
            
            _LOGGER.critical(f"Using headers: {headers}")
            
            async with session.get(api_url, headers=headers, ssl=False) as resp:
                if resp.status == 401:  # Token abgelaufen
                    _LOGGER.critical("VCF token expired (401), attempting to refresh")
                    
                    new_token = await refresh_vcf_token()
                    if new_token:
                        # Erneuter Versuch mit neuem Token
                        headers["Authorization"] = f"Bearer {new_token}"
                        _LOGGER.critical("Retrying with new token")
                        
                        async with session.get(api_url, headers=headers, ssl=False) as retry_resp:
                            if retry_resp.status != 200:
                                error_text = await retry_resp.text()
                                _LOGGER.critical(f"VCF API retry failed: {retry_resp.status}, {error_text}")
                                return {"upgradable_data": {"elements": []}}
                            
                            raw_data = await retry_resp.json()
                            _LOGGER.critical(f"VCF API success after token refresh, response type: {type(raw_data)}")
                    else:
                        _LOGGER.critical("Failed to refresh token")
                        return {"upgradable_data": {"elements": []}}
                elif resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.critical(f"VCF API returned error {resp.status}: {error_text}")
                    return {"upgradable_data": {"elements": []}}
                else:
                    raw_data = await resp.json()
                    _LOGGER.critical(f"VCF API initial call successful, response type: {type(raw_data)}")
                
                # Log vollständige Antwort für Analyse
                _LOGGER.critical(f"Complete VCF API response: {raw_data}")
                
                # Datenstruktur analysieren
                if isinstance(raw_data, dict):
                    _LOGGER.critical(f"VCF response is dict with keys: {raw_data.keys()}")
                    for key in raw_data.keys():
                        try:
                            _LOGGER.critical(f"VCF key '{key}' type: {type(raw_data[key])}")
                            if isinstance(raw_data[key], (list, dict)):
                                sample = raw_data[key]
                                if isinstance(sample, list) and len(sample) > 0:
                                    _LOGGER.critical(f"First item in '{key}': {sample[0]}")
                                elif isinstance(sample, dict) and len(sample) > 0:
                                    first_subkey = list(sample.keys())[0] if sample else "none"
                                    _LOGGER.critical(f"Sample from '{key}', subkey '{first_subkey}': {sample.get(first_subkey)}")
                        except Exception as e:
                            _LOGGER.critical(f"Error analyzing key '{key}': {e}")
                
                elif isinstance(raw_data, list):
                    _LOGGER.critical(f"VCF response is list with {len(raw_data)} items")
                    if raw_data and len(raw_data) > 0:
                        _LOGGER.critical(f"First item: {raw_data[0]}")
                else:
                    _LOGGER.critical(f"VCF response is unexpected type: {type(raw_data)}")
                
                # Normalisierung der Datenstruktur
                if isinstance(raw_data, list):
                    _LOGGER.critical("Converting list response to elements dict")
                    normalized_data = {"elements": raw_data}
                elif isinstance(raw_data, dict):
                    if "content" in raw_data and isinstance(raw_data["content"], list):
                        _LOGGER.critical("Found content list in response")
                        normalized_data = {"elements": raw_data["content"]}
                    elif "elements" in raw_data:
                        _LOGGER.critical("Using existing elements in response")
                        normalized_data = raw_data
                    elif "items" in raw_data and isinstance(raw_data["items"], list):
                        _LOGGER.critical("Found items list in response")
                        normalized_data = {"elements": raw_data["items"]}
                    else:
                        # Wenn keine bekannte Struktur gefunden wird, versuchen wir, die erste Liste zu verwenden
                        list_found = False
                        for key, value in raw_data.items():
                            if isinstance(value, list):
                                _LOGGER.critical(f"Using list found in key '{key}'")
                                normalized_data = {"elements": value}
                                list_found = True
                                break
                        
                        if not list_found:
                            _LOGGER.critical("No usable list structure found in response")
                            normalized_data = {"elements": []}
                else:
                    _LOGGER.critical("Cannot normalize unexpected response type")
                    normalized_data = {"elements": []}
                
                _LOGGER.critical(f"Normalized VCF data structure: {normalized_data}")
                return {"upgradable_data": normalized_data}
                
        except aiohttp.ClientError as e:
            _LOGGER.critical(f"VCF connection error: {e}")
            return {"upgradable_data": {"elements": []}}
        except Exception as e:
            _LOGGER.critical(f"VCF Upgrade fetch failed: {e}")
            _LOGGER.exception("Detailed exception info")  # Diese Zeile gibt den vollständigen Stack-Trace aus
            return {"upgradable_data": {"elements": []}}

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
