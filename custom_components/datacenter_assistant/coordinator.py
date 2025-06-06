import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

def get_coordinator(hass, config_entry):
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")

    # Proxmox-Daten für kombinierte Funktionalität
    ip_address = config_entry.data.get("ip_address")
    port = config_entry.data.get("port", 8006)
    api_token_id = config_entry.data.get("api_token_id", "")
    api_token_secret = config_entry.data.get("api_token_secret", "")
    node = config_entry.data.get("node", "")
    vmid = config_entry.data.get("vmid", "")

    headers = {
        "Authorization": f"Bearer {vcf_token}",
        "Accept": "application/json"
    }

    async def async_fetch_proxmox_data():
        """Fetch Proxmox VM status data."""
        if not ip_address or not api_token_id or not api_token_secret or not node or not vmid:
            return {"status": "unknown", "error": "Missing configuration"}
            
        session = async_get_clientsession(hass)
        base_url = f"https://{ip_address}:{port}/api2/json"
        
        try:
            # Konstruktion des Authorization Headers
            auth_str = f"{api_token_id}={api_token_secret}"
            auth_header = {"Authorization": f"PVEAPIToken {auth_str}"}
            
            _LOGGER.debug(f"Connecting to Proxmox: {base_url} with token ID: {api_token_id}")
            
            url = f"{base_url}/nodes/{node}/qemu/{vmid}/status/current"
            async with session.get(url, headers=auth_header, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Proxmox API error: {resp.status}, {error_text}")
                    return {"status": "unknown", "error": error_text}
                
                data = await resp.json()
                _LOGGER.debug(f"Proxmox API response: {data}")
                return data.get("data", {})
        except Exception as e:
            _LOGGER.error(f"Proxmox connection error: {e}")
            return {"status": "unknown", "error": str(e)}

    async def async_fetch_upgrades():
        _LOGGER.debug("VCF Coordinator async_fetch_upgrades() is being called")

        session = async_get_clientsession(hass)

        # Proxmox-Daten vorher holen
        proxmox_data = await async_fetch_proxmox_data()

        # MOCKDATEN bei fehlender Konfiguration
        if not vcf_url or not vcf_token:
            _LOGGER.warning("VCF not configured — using mock upgrade data.")
            return {
                "upgradable_data": {
                    "elements": [
                        {
                            "status": "AVAILABLE",
                            "resource": {
                                "fqdn": "esxi01.lab.local",
                                "type": "ESXI"
                            }
                        },
                        {
                            "status": "PENDING",
                            "resource": {
                                "fqdn": "esxi02.lab.local",
                                "type": "ESXI"
                            }
                        },
                        {
                            "status": "SCHEDULED",
                            "resource": {
                                "fqdn": "nsx.lab.local",
                                "type": "NSX_MANAGER"
                            }
                        }
                    ]
                },
                "proxmox_data": proxmox_data
            }

        # ECHTER API-ABRUF
        try:
            api_url = f"{vcf_url}/v1/system/upgradables"
            _LOGGER.debug(f"Attempting to fetch VCF data from: {api_url}")
            
            async with session.get(api_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"VCF API returned status {resp.status}: {error_text}")
                    raise UpdateFailed(f"Error {resp.status} from VCF API: {error_text}")
                
                raw_data = await resp.json()
                _LOGGER.debug(f"VCF API raw response: {raw_data}")
                
                # Datenstruktur analysieren
                if "elements" not in raw_data and isinstance(raw_data, dict):
                    _LOGGER.debug(f"Analyzing VCF response structure. Keys: {raw_data.keys()}")
                
                # Normalisierung der Datenstruktur
                # Wenn raw_data selbst bereits eine Liste ist
                if isinstance(raw_data, list):
                    normalized_data = {"elements": raw_data}
                # Wenn raw_data ein Dict ist mit einem "content"-Schlüssel oder einem anderen Unterfeld
                elif isinstance(raw_data, dict):
                    if "content" in raw_data and isinstance(raw_data["content"], list):
                        normalized_data = {"elements": raw_data["content"]}
                    elif "elements" in raw_data:
                        normalized_data = raw_data  # Bereits im erwarteten Format
                    elif "items" in raw_data and isinstance(raw_data["items"], list):
                        normalized_data = {"elements": raw_data["items"]}
                    # Fallback für leeres Ergebnis
                    else:
                        _LOGGER.warning(f"Unknown VCF API response structure: {raw_data}")
                        normalized_data = {"elements": []}
                else:
                    _LOGGER.warning(f"Unexpected VCF API response type: {type(raw_data)}")
                    normalized_data = {"elements": []}
                
                _LOGGER.debug(f"Normalized VCF data: {normalized_data}")
                
                # Kombiniere VCF und Proxmox Daten
                return {
                    "upgradable_data": normalized_data,
                    "proxmox_data": proxmox_data
                }
        except aiohttp.ClientError as e:
            _LOGGER.error(f"VCF connection error: {e}")
            raise UpdateFailed(f"Connection error: {e}")
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch failed: {e}")

            # Fallback mit Mockdaten bei Fehler
            return {
                "upgradable_data": {
                    "elements": [
                        {
                            "status": "UNAVAILABLE",
                            "resource": {
                                "fqdn": "mock.lab.local",
                                "type": "UNKNOWN"
                            }
                        }
                    ]
                },
                "proxmox_data": proxmox_data
            }

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
