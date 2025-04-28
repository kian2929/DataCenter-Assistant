import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    async_add_entities([ProxmoxStatusSensor(hass, entry)], True)

class ProxmoxStatusSensor(SensorEntity):
    """Representation of a Proxmox Cluster Status Sensor."""

    def __init__(self, hass, entry):
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._state = STATE_UNKNOWN
        self._attr_name = "Proxmox Cluster Status"
        self._attr_unique_id = "proxmox_cluster_status"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon depending on the state."""
        if self._state == "online":
            return "mdi:server-network" 
        elif self._state == "offline":
            return "mdi:server-network-off"
        else:
            return "mdi:server"

    async def async_update(self):
        """Fetch new state data for the sensor."""
        ip_address = self._entry.data.get("ip_address")
        port = self._entry.data.get("port")
        api_token_id = self._entry.data.get("api_token_id")
        api_token_secret = self._entry.data.get("api_token_secret")

        url = f"https://{ip_address}:{port}/api2/json/cluster/status"
        headers = {
            "Authorization": f"PVEAPIToken={api_token_id}={api_token_secret}"
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

                _LOGGER.error("Proxmox API Response: %s", data)

                node_info = data["data"][0]
                node_online = node_info.get("online", 0)

                self._state = "online" if node_online else "offline"
                _LOGGER.info("Proxmox Node Status: %s", self._state)

        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen des Proxmox Status: %s", e)
            self._state = STATE_UNKNOWN
