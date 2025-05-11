import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import CONF_HOST
import logging

_LOGGER = logging.getLogger(__name__)

VCF_API = "https://your-vcf-host.example.com"
TOKEN = "your_bearer_token"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

async def async_fetch_upgrades():
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch the primary upgrade data from the first endpoint
            async with session.get(f"{VCF_API}/v1/system/upgradables", headers=HEADERS) as resp:
                resp.raise_for_status()
                upgradable_data = await resp.json()

            # Fetch the additional data from the second endpoint
            async with session.get(f"{VCF_API}/v1/system/another_endpoint", headers=HEADERS) as resp2:
                resp2.raise_for_status()
                additional_data = await resp2.json()

            # Combine the data from both endpoints under distinct keys
            combined_data = {
                'upgradable_data': upgradable_data,
                'additional_data': additional_data,
            }
            return combined_data
    except Exception as e:
        _LOGGER.error(f"Error fetching data: {e}")
        raise UpdateFailed(f"Error fetching data: {e}")