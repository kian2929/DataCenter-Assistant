# import aiohttp
# import logging
# from datetime import timedelta
# from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
# from homeassistant.helpers.aiohttp_client import async_get_clientsession

# _LOGGER = logging.getLogger(__name__)

# def get_coordinator(hass, config_entry):
#     vcf_url = config_entry.data.get("vcf_url")
#     vcf_token = config_entry.data.get("vcf_token")

#     headers = {
#         "Authorization": f"Bearer {vcf_token}",
#         "Accept": "application/json"
#     }

#     async def async_fetch_upgrades():
#         session = async_get_clientsession(hass)
#         LOGGER.debug("Fetching VCF data from: %s", vcf_url)

#         # MOCKDATEN bei fehlender Konfiguration
#         if not vcf_url or not vcf_token:
#             _LOGGER.warning("VCF not configured — using mock upgrade data.")
#             return {
#                 "upgradable_data": {
#                     "elements": [
#                         {
#                             "status": "AVAILABLE",
#                             "resource": {
#                                 "fqdn": "esxi01.lab.local",
#                                 "type": "ESXI"
#                             }
#                         },
#                         {
#                             "status": "PENDING",
#                             "resource": {
#                                 "fqdn": "esxi02.lab.local",
#                                 "type": "ESXI"
#                             }
#                         },
#                         {
#                             "status": "SCHEDULED",
#                             "resource": {
#                                 "fqdn": "nsx.lab.local",
#                                 "type": "NSX_MANAGER"
#                             }
#                         }
#                     ]
#                 }
#             }

#         # ECHTER API-ABRUF
#         try:
#             async with session.get(f"{vcf_url}/v1/system/upgradables", headers=headers, ssl=False) as resp:
#                 resp.raise_for_status()
#                 return {
#                     "upgradable_data": await resp.json()
#                 }
#         except Exception as e:
#             _LOGGER.error(f"VCF Upgrade fetch failed: {e}")
#             # Optionaler Fallback mit Mockdaten bei Fehler
#             return {
#                 "upgradable_data": {
#                     "elements": [
#                         {
#                             "status": "UNAVAILABLE",
#                             "resource": {
#                                 "fqdn": "mock.lab.local",
#                                 "type": "UNKNOWN"
#                             }
#                         }
#                     ]
#                 }
#             }

#     return DataUpdateCoordinator(
#         hass,
#         _LOGGER,
#         name="VCF Upgrades",
#         update_method=async_fetch_upgrades,
#         update_interval=timedelta(minutes=15),
#     )
import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class VCFUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.vcf_url = config_entry.data.get("vcf_url")
        self.vcf_token = config_entry.data.get("vcf_token")
        self.session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name="VCF Update Coordinator",
            update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self):
        _LOGGER.warning("VCFCoordinator: _async_update_data called")
        headers = {
            "Authorization": f"Bearer {self.vcf_token}",
            "Accept": "application/json",
        }

        if not self.vcf_url or not self.vcf_token:
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

        try:
            url = f"{self.vcf_url}/api/v1/system/upgradables"
            async with self.session.get(url, headers=headers, ssl=False, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("VCF data received: %s", data)
                return {
                    "upgradable_data": data
                }
        except Exception as e:
            _LOGGER.warning("Error determining VCF upgrade status: %s", e)
            raise UpdateFailed(f"Error fetching VCF data: {e}")


def get_coordinator(hass, config_entry):
    coordinator = VCFUpdateCoordinator(hass, config_entry)
    _LOGGER.warning(f"Got coordinator: {coordinator}")
    return coordinator
