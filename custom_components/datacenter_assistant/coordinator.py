import aiohttp
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

def get_coordinator(hass, config_entry):
    vcf_url = config_entry.data.get("vcf_url")
    vcf_token = config_entry.data.get("vcf_token")

    if not vcf_url or not vcf_token:
        raise ValueError("VCF URL or token not configured")

    headers = {
        "Authorization": f"Bearer {vcf_token}",
        "Accept": "application/json"
    }

    async def async_fetch_upgrades():
        session = async_get_clientsession(hass)

        try:
            async with session.get(f"{vcf_url}/v1/system/upgradables", headers=headers, ssl=False) as resp:
                resp.raise_for_status()
                return {"upgradable_data": await resp.json()}
        except Exception as e:
            _LOGGER.error(f"VCF Upgrade fetch failed: {e}")
            raise UpdateFailed(f"VCF fetch failed: {e}")

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="VCF Upgrades",
        update_method=async_fetch_upgrades,
        update_interval=timedelta(minutes=15),
    )
