import asyncio
import aiohttp
import voluptuous as vol
from typing import Optional
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_TIMEOUT, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import DOMAIN
from .nec_api import NECAPI

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60
DEFAULT_PORT = 7142


class NecConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for NEC (LAN Control - Port 7142)."""

    async def _async_get_device_info(
        self, host: str, port: int, monitor_id: int, timeout: int
    ) -> Optional[dict]:
        """Try to get device info from the NEC device via LAN."""
        try:
            async with asyncio.timeout(timeout):
                nec_api = NECAPI(host, port, monitor_id, timeout)
                if await nec_api.connect():
                    device_info = await nec_api.get_device_info()
                    await nec_api.close()
                    if (
                        device_info
                        and device_info.get("manufacturer") == "NEC"
                    ):
                        return device_info
                    elif device_info:
                        _LOGGER.warning(
                            f"Device at {host}:{port} identified as: {device_info.get('model_name')}, but might not be fully compatible."
                        )
                        return device_info
                    else:
                        _LOGGER.warning(
                            f"Could not retrieve device info from {host}:{port} via LAN Control."
                        )
                        return None
                else:
                    return None
        except asyncio.TimeoutError:
            _LOGGER.error(
                f"Timeout of {timeout} seconds connecting to {host}:{port} via LAN Control."
            )
            return None
        except Exception as e:
            _LOGGER.error(
                f"Unexpected error during LAN Control device info retrieval: {e}"
            )
            return None

    async def async_step_user(self, user_input: Optional[dict] = None) -> dict:
        """Handle the initial step of the config flow."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            monitor_id = user_input[vol.Required("monitor_id", default=1)]
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

            device_info = await self._async_get_device_info(
                host, port, monitor_id, timeout
            )

            if device_info:
                await self.async_set_unique_id(
                    device_info.get("serial_number")
                    or f"{host}-{port}-{monitor_id}"
                )
                self._abort_if_unique_id_configured()
                user_input["port"] = port  # Ensure port is in the final data
                return self.async_create_entry(
                    title=device_info.get("model_name") or host,
                    data=user_input,
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Required("monitor_id", default=1): int,
                    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_import(self, user_input: dict) -> dict:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)

    async def async_step_zeroconf(self, discovery_info: dict) -> dict:
        """Handle zeroconf discovery (if applicable)."""
        host = discovery_info.host
        return await self.async_step_user({CONF_HOST: host})

    async def async_step_reauth(self, user_input: dict) -> dict:
        """Handle reauth."""
        return await self.async_step_user(user_input)

    async def async_step_options(
        self, user_input: Optional[dict] = None
    ) -> dict:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int}
            ),
        )
