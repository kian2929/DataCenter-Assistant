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
    
    # Besseres Debug-Logging
    _LOGGER.debug(f"Initializing VCF coordinator with URL: {vcf_url}")
    _LOGGER.debug("TESTLOG: Komponente datacenter_assistant wurde geladen")

    # Mutable token zur Aktualisierung
    token_data = {"access_token": vcf_token, "refresh_token": vcf_refresh_token}
    
    headers = {
        "Authorization": f"Bearer {token_data['access_token']}",
        "Accept": "application/json"
    }

    async def refresh_token_with_refresh_token():
        """Erneuert den Access-Token mit einem Refresh-Token."""
        if not vcf_url or not token_data["refresh_token"]:
            _LOGGER.warning("Cannot refresh token: Missing refresh token")
            return False
            
        try:
            session = async_get_clientsession(hass)
            refresh_url = f"{vcf_url}/v1/tokens/refresh"  # Anpassen an den tatsächlichen Endpoint
            
            refresh_data = {
                "refresh_token": token_data["refresh_token"]
            }
            
            _LOGGER.debug(f"Attempting to refresh token with refresh token at: {refresh_url}")
            
            async with session.post(refresh_url, json=refresh_data, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Token refresh failed: {resp.status}, {error_text}")
                    return False
                    
                response_data = await resp.json()
                _LOGGER.debug(f"Token refresh response: {response_data}")
                
                # Extrahiere die neuen Tokens
                new_access_token = response_data.get("access_token") or response_data.get("accessToken")
                new_refresh_token = response_data.get("refresh_token") or response_data.get("refreshToken")
                
                if new_access_token:
                    # Aktualisiere die Token-Daten
                    token_data["access_token"] = new_access_token
                    if new_refresh_token:
                        token_data["refresh_token"] = new_refresh_token
                    
                    # Aktualisiere den Header
                    headers["Authorization"] = f"Bearer {new_access_token}"
                    
                    # Speichere die Tokens in der Konfiguration
                    new_data = dict(config_entry.data)
                    new_data["vcf_token"] = new_access_token
                    if new_refresh_token:
                        new_data["vcf_refresh_token"] = new_refresh_token
                    
                    hass.config_entries.async_update_entry(
                        config_entry,
                        data=new_data
                    )
                    
                    _LOGGER.info("Successfully refreshed access token using refresh token")
                    return True
                else:
                    _LOGGER.error("Failed to extract new access token from response")
                    return False
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing token with refresh token: {e}")
            return False

    async def refresh_token_with_credentials():
        """Erneuert den Access-Token mit Benutzername und Passwort."""
        if not vcf_url or not vcf_username or not vcf_password:
            _LOGGER.warning("Cannot refresh token: Missing credentials")
            return False
            
        try:
            session = async_get_clientsession(hass)
            login_url = f"{vcf_url}/v1/tokens"
            
            auth_data = {
                "username": vcf_username,
                "password": vcf_password
            }
            
            _LOGGER.debug(f"Attempting to refresh token with credentials at: {login_url}")
            
            async with session.post(login_url, json=auth_data, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Token refresh failed: {resp.status}, {error_text}")
                    return False
                    
                response_data = await resp.json()
                _LOGGER.debug(f"Token refresh response: {response_data}")
                
                # Extrahiere die neuen Tokens
                new_access_token = response_data.get("access_token") or response_data.get("accessToken")
                new_refresh_token = response_data.get("refresh_token") or response_data.get("refreshToken")
                
                if new_access_token:
                    # Aktualisiere die Token-Daten
                    token_data["access_token"] = new_access_token
                    if new_refresh_token:
                        token_data["refresh_token"] = new_refresh_token
                    
                    # Aktualisiere den Header
                    headers["Authorization"] = f"Bearer {new_access_token}"
                    
                    # Speichere die Tokens in der Konfiguration
                    new_data = dict(config_entry.data)
                    new_data["vcf_token"] = new_access_token
                    if new_refresh_token:
                        new_data["vcf_refresh_token"] = new_refresh_token
                    
                    hass.config_entries.async_update_entry(
                        config_entry,
                        data=new_data
                    )
                    
                    _LOGGER.info("Successfully refreshed tokens using credentials")
                    return True
                else:
                    _LOGGER.error("Failed to extract new access token from response")
                    return False
                    
        except Exception as e:
            _LOGGER.error(f"Error refreshing token with credentials: {e}")
            return False

    async def refresh_tokens():
        """Versucht verschiedene Methoden, um den Token zu erneuern."""
        # Versuche zuerst mit Refresh-Token
        if token_data["refresh_token"]:
            if await refresh_token_with_refresh_token():
                return True
            
            _LOGGER.warning("Refresh token failed, trying with credentials")
        
        # Wenn das fehlschlägt oder kein Refresh-Token existiert, verwende Credentials
        return await refresh_token_with_credentials()

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
                "Authorization": f"Bearer {token_data['access_token']}",
                "Accept": "application/json"
            }
            
            async with session.get(api_url, headers=current_headers, ssl=False) as resp:
                if resp.status == 401:  # Token abgelaufen
                    _LOGGER.warning("VCF token expired, attempting refresh")
                    
                    if await refresh_tokens():
                        # Token erfolgreich aktualisiert, erneuter Versuch
                        _LOGGER.debug("Retrying with new token")
                        async with session.get(api_url, headers={
                            "Authorization": f"Bearer {token_data['access_token']}",
                            "Accept": "application/json"
                        }, ssl=False) as retry_resp:
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
