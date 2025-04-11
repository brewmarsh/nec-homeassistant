"""DataUpdateCoordinator for NEC integration."""

import logging
from datetime import timedelta

from aiohttp.client_exceptions import (
    ClientConnectionError,
    ClientResponseError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN  # Updated import
from .nec_api import NECAPI  # Assuming you'll create this

_LOGGER = logging.getLogger(__name__)


class NecDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the NEC device."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry
        self.nec_api = NECAPI(
            host=config_entry.data[CONF_HOST],
            port=config_entry.data.get(CONF_PORT, 7142),
            monitor_id=config_entry.data.get("monitor_id", 1),
            timeout=config_entry.data.get(CONF_TIMEOUT, 5),
        )
        self._device_info = None  # Initialize to None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,  # Updated domain
            update_interval=timedelta(
                seconds=60
            ),  # Configurable update interval
        )

    async def async_config_entry_first_refresh(self) -> None:
        """Handle a config entry first refresh."""
        await super().async_config_entry_first_refresh()
        self._device_info = await self._async_get_device_info()  # Await here

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    async def _async_get_device_info(self) -> DeviceInfo:
        """Get the device information."""
        device_data = {}
        try:
            device_data = (
                await self.nec_api.get_device_info()
            )  # Implement this in NECAPI
            _LOGGER.debug(f"Device info retrieved: {device_data}")
        except (ClientConnectionError, ClientResponseError) as error:
            _LOGGER.warning(
                f"Error communicating with device to get device info: {error}"
            )
        except Exception as exception:
            _LOGGER.warning(f"Error fetching device info: {exception}")

        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.unique_id)},
            name=self.config_entry.title,
            manufacturer=device_data.get("manufacturer", "NEC"),
            model=device_data.get("model_name", "Projector"),
            sw_version=device_data.get("firmware_version"),
        )

    async def _async_update_data(self):
        """Fetch data from the device."""
        try:
            data = (
                await self.nec_api.get_all_data()
            )  # Implement this in NECAPI
            return data
        except (ClientConnectionError, ClientResponseError) as error:
            raise UpdateFailed(
                f"Error communicating with device: {error}"
            ) from error
        except Exception as exception:
            raise UpdateFailed(
                f"Error fetching data: {exception}"
            ) from exception


class NecDeviceCoordinator:  # You might need this to coordinate device creations
    """Class to manage device creation."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.devices = {}

    async def get_or_create_device(self, device_info: dict) -> dict:
        """Get or create a device entity."""
        device_id = device_info.get("serial_number")  # Or some other unique ID
        if device_id and device_id not in self.devices:
            # Create device entity here (e.g., using a helper function)
            self.devices[device_id] = self._create_device(device_info)
        return self.devices.get(
            device_id, device_info
        )  # Return existing or the info

    def _create_device(self, device_info: dict) -> dict:
        """Create a device entity."""
        # Implement device creation logic here
        return device_info  # Replace with actual device object/entity creation
