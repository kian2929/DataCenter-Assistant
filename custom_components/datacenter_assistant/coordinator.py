import aiohttp
import logging
import time
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
        """Fetch VCF upgrade information."""
        _LOGGER.debug("VCF Coordinator refreshing data")
        
        # Prüfe, ob VCF konfiguriert ist
        if not vcf_url:
            _LOGGER.warning("VCF not configured with URL")
            return {"upgradable_data": {"elements": []}}

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
                # return {
                #     "upgradable_data": {
                #         "elements": [
                #             {
                #                 "resource": {
                #                     "fqdn": "esxi01.lab.local",
                #                     "type": "ESXI"
                #                 },
                #                 "status": "AVAILABLE",
                #                 "description": "ESXi Update 7.0.3"
                #             },
                #             {
                #                 "resource": {
                #                     "fqdn": "nsx.lab.local",
                #                     "type": "NSX"
                #                 },
                #                 "status": "PENDING",
                #                 "description": "NSX Update 4.0.1"
                #             }
                #         ]
                #     }
                # }
                
                # Original code (auskommentieren für Tests)
                return {"upgradable_data": normalized_data}
            
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
