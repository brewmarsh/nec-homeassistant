"""The NEC integration."""

import asyncio
import logging
import os  #  Import the os module

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import NecDataUpdateCoordinator
from .version import VERSION, BUILD, FULL_VERSION

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry for the NEC integration."""
    _LOGGER.debug(
        f"Setting up entry: {entry.title} with data: {entry.data}, Version: {FULL_VERSION}"
    )

    coordinator = NecDataUpdateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as error:
        _LOGGER.error(f"Config entry not ready: {error}")
        raise ConfigEntryNotReady from error
    except Exception as error:
        _LOGGER.error(f"Unexpected error during setup: {error}")
        return False  # Indicate setup failure

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up platforms (sensors, switches)
    results = await asyncio.gather(
        *[
            hass.config_entries.async_forward_entry_setups(
                entry, ("sensor", "switch")
            )
        ]
    )

    # Check if all platforms were successfully set up
    if all(results):
        _LOGGER.info(
            f"Successfully set up platforms for {entry.title}"
        )  # Log platform setup success
        return True
    else:
        _LOGGER.warning(
            f"Failed to set up all platforms for {entry.title}"
        )  # Log platform setup failure
        # If any platform setup failed, unload the entry
        await async_unload_entry(hass, entry)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        f"Unloading entry: {entry.title}, Version: {FULL_VERSION}"
    )  # Log entry unloading with version
    unload_ok = await asyncio.gather(
        *[
            hass.config_entries.async_forward_entry_unload(entry, platform)
            for platform in ("sensor", "switch")
        ]
    )
    if all(unload_ok):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info(
            f"Successfully unloaded all platforms for {entry.title}"
        )  # Log platform unload success
        return True
    else:
        _LOGGER.warning(
            f"Failed to unload all platforms for {entry.title}"
        )  # Log platform unload failure
        return False


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    _LOGGER.info(
        f"Reloading entry: {entry.title}, Version: {FULL_VERSION}"
    )  # Log entry reloading with version
    try:
        await hass.config_entries.async_reload(entry.entry_id)
        _LOGGER.info(
            f"Successfully reloaded entry: {entry.title}"
        )  # Log reload success
    except Exception as error:
        _LOGGER.error(f"Error reloading entry: {error}")  # Log reload failure
