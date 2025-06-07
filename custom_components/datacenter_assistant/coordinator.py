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
        """Fetch VCF bundle information."""
        _LOGGER.debug("VCF Coordinator refreshing bundle data")
        
        # Prüfe, ob VCF konfiguriert ist
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"bundle_data": {"elements": []}}

        current_token = config_entry.data.get("vcf_token")
        current_expiry = config_entry.data.get("token_expiry", 0)
        
        # Prüfen, ob das Token in weniger als 10 Minuten abläuft
        if current_expiry > 0 and time.time() > current_expiry - 600:  # 10 Minuten vor Ablauf
            _LOGGER.info("VCF token will expire soon, refreshing proactively")
            new_token = await refresh_vcf_token()
            if new_token:
                current_token = new_token
            else:
                _LOGGER.warning("Failed to refresh token proactively")
        
        # API-ABRUF mit Retry-Mechanismus
        max_retries = 3
        retry_delay = 5  # Sekunden
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                session = async_get_clientsession(hass)
                # Neuer Endpunkt für Bundle-Management
                api_url = f"{vcf_url}/v1/bundles"
                
                headers = {
                    "Authorization": f"Bearer {current_token}",
                    "Accept": "application/json"
                }
                
                # Bei Wiederholungsversuch eine Nachricht ausgeben
                if attempt > 0:
                    _LOGGER.info(f"Retry attempt {attempt+1}/{max_retries} for VCF Bundles API")
                
                # Parameter für die Filterung
                params = {
                    "isCompliant": "true",  # Nur kompatible Bundles anzeigen
                    "productType": "vcf"     # Auf VCF-Produkte filtern
                }
                
                async with session.get(api_url, headers=headers, params=params, ssl=False) as resp:
                    if resp.status == 401:  # Token abgelaufen
                        _LOGGER.info("VCF token expired, refreshing...")
                        
                        new_token = await refresh_vcf_token()
                        if new_token:
                            headers["Authorization"] = f"Bearer {new_token}"
                            _LOGGER.debug("Retrying with new token")
                            
                            async with session.get(api_url, headers=headers, params=params, ssl=False) as retry_resp:
                                if retry_resp.status != 200:
                                    _LOGGER.error(f"VCF Bundles API retry failed: {retry_resp.status}")
                                    # Bei Fehler nach Token-Erneuerung weiter wiederholen
                                    raise aiohttp.ClientError(f"API returned status {retry_resp.status} after token refresh")
                                
                                raw_data = await retry_resp.json()
                        else:
                            _LOGGER.warning("Failed to refresh token")
                            raise aiohttp.ClientError("Failed to refresh token")
                    elif resp.status != 200:
                        _LOGGER.error(f"VCF Bundles API error: {resp.status}")
                        raise aiohttp.ClientError(f"API returned status {resp.status}")
                    else:
                        raw_data = await resp.json()
                        _LOGGER.debug(f"VCF Bundles API success, response: {raw_data}")
                    
                    # Normalisierung der Datenstruktur für Bundles
                    bundles_data = {"elements": []}
                    
                    # PageOfBundle Struktur verarbeiten
                    if isinstance(raw_data, dict):
                        if "elements" in raw_data:
                            bundles_list = raw_data["elements"]
                        elif "content" in raw_data:
                            bundles_list = raw_data["content"]
                        elif "bundles" in raw_data:
                            bundles_list = raw_data["bundles"]
                        elif "items" in raw_data:
                            bundles_list = raw_data["items"]
                        else:
                            bundles_list = []
                            _LOGGER.warning(f"Unbekannte Antwortstruktur: {raw_data.keys()}")
                    elif isinstance(raw_data, list):
                        bundles_list = raw_data
                    else:
                        bundles_list = []
                        _LOGGER.warning(f"Unerwarteter Antworttyp: {type(raw_data)}")
                    
                    # Filter nach "VMware Cloud Foundation" in der Beschreibung
                    filtered_bundles = []
                    for bundle in bundles_list:
                        description = bundle.get("description", "").lower()
                        name = bundle.get("name", "").lower()
                        
                        if "vmware cloud foundation" in description:
                            filtered_bundles.append(bundle)
                            _LOGGER.debug(f"VCF Bundle gefunden: {bundle.get('name')}")
                        elif "vcf" in name:
                            filtered_bundles.append(bundle)
                            _LOGGER.debug(f"VCF Bundle gefunden (via Name): {bundle.get('name')}")
                    
                    bundles_data["elements"] = filtered_bundles
                    
                    # Erfolgreicher Aufruf, Return hier
                    return {"bundle_data": bundles_data, "upgradable_data": {"elements": []}}
                
            except aiohttp.ClientError as e:
                last_exception = e
                _LOGGER.warning(f"VCF connection error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Exponentielles Backoff für Wiederholungen
                    wait_time = retry_delay * (2 ** attempt)  # 5, 10, 20 Sekunden
                    _LOGGER.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error(f"VCF connection failed after {max_retries} attempts: {e}")
            except Exception as e:
                _LOGGER.error(f"Unexpected error fetching VCF bundle data: {e}")
                last_exception = e
                break  # Bei unerwarteten Fehlern nicht wiederholen
        
        # Wenn wir hier ankommen, waren alle Versuche erfolglos
        return {"bundle_data": {"elements": []}, "upgradable_data": {"elements": []}}

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
