import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

def get_coordinator(hass, config_entry):
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")

    headers = {
        "Authorization": f"Bearer {vcf_token}",
        "Accept": "application/json"
    }

    async def async_fetch_upgrades():
        _LOGGER.debug("VCF Coordinator async_fetch_upgrades() is being called")

        session = async_get_clientsession(hass)

        # MOCKDATEN bei fehlender Konfiguration test
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
                }
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
                
                data = await resp.json()
                _LOGGER.debug(f"VCF API response: {data}")
                return {
                    "upgradable_data": data
                }
        except aiohttp.ClientError as e:
            _LOGGER.error(f"VCF connection error: {e}")
            raise UpdateFailed(f"Connection error: {e}")
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch failed: {e}")

            # Optionaler Fallback mit Mockdaten bei Fehler
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
                }
            }

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
