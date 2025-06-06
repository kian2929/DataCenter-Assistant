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
        print("DEBUG: Coordinator async_fetch_upgrades() is being called")

        session = async_get_clientsession(hass)

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
                }
            }

        # ECHTER API-ABRUF
        try:

            async with session.get(f"{vcf_url}/v1/system/upgradables", headers=headers, ssl=False) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return {
                    "upgradable_data": data
                }
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch failed: {e}")
            print(f"DEBUG: Exception occurred in async_fetch_upgrades(): {e}")

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
