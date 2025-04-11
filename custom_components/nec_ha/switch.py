"""Switch platform for NEC integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NecDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: NecDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities(
        [
            NecPowerSwitch(coordinator, hass),
            # Add other switches here
        ]
    )


class NecPowerSwitch(SwitchEntity):
    """Representation of a NEC power switch."""

    def __init__(
        self, coordinator: NecDataUpdateCoordinator, hass: HomeAssistant
    ) -> None:
        """Initialize the switch."""
        self.coordinator = coordinator
        self.hass = hass
        self._attr_name = "NEC Power"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_power"
        self._attr_is_on = (
            self._get_power_state()
        )  # Initialize with current state

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """Return the current power state."""
        return self._get_power_state()

    def _get_power_state(self) -> bool:
        """Get the latest power state from coordinator data."""
        power_status = self.coordinator.data.get("power_status")
        return power_status == STATE_ON

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the device on."""
        try:
            await self.coordinator.nec_api.set_power(STATE_ON)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Error turning on device: {e}")
            #  Consider raising an exception or setting an error state

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        try:
            await self.coordinator.nec_api.set_power(STATE_OFF)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Error turning off device: {e}")
            #  Consider raising an exception or setting an error state

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": "NEC Device",  # Get from coordinator data
            "manufacturer": "NEC",  # Get from coordinator data
            "model": "NEC Projector",  # Get from coordinator data
            "sw_version": "1.0",  # Get from coordinator data
        }

    async def async_update(self) -> None:
        """Update the switch."""
        await self.coordinator.async_request_refresh()
