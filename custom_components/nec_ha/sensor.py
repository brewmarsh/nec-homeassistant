"""Sensor platform for NEC integration."""

import logging
from typing import Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    _LOGGER.debug("async_setup_entry: Starting sensor platform setup")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug(f"async_setup_entry: Coordinator: {coordinator}")
    _LOGGER.debug(
        f"async_setup_entry: Coordinator device_info: {coordinator.device_info}"
    )

    entities = [
        NecTemperatureSensor(coordinator, config_entry),
        NecLampHoursSensor(coordinator, config_entry),
    ]
    _LOGGER.debug(f"async_setup_entry: Created entities: {entities}")
    async_add_entities(entities)
    _LOGGER.debug("async_setup_entry: Finished adding entities")


class NecSensor(CoordinatorEntity, SensorEntity):
    """Base class for NEC sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CoordinatorEntity,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        _LOGGER.debug(
            f"NecSensor.__init__: Coordinator device_info in base class: {coordinator.device_info}"
        )
        # self._attr_device_info = coordinator.device_info  <- Remove this line
        _LOGGER.debug(
            f"NecSensor.__init__: self._attr_device_info (initial): {getattr(self, '_attr_device_info', None)}"
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._attr_device_info = self.coordinator.device_info
        _LOGGER.debug(
            f"NecSensor.async_added_to_hass: self._attr_device_info set to: {self._attr_device_info}"
        )

    @property
    def unique_id(self) -> Optional[str]:
        """Return the unique ID of the sensor."""
        serial = self.coordinator.device_info.get("serial_number")
        if serial:
            uid = f"{self.config_entry.entry_id}-{serial}-{self.__class__.__name__.lower()}"
        else:
            uid = f"{self.config_entry.entry_id}-{self.__class__.__name__.lower()}"
        _LOGGER.debug(f"NecSensor.unique_id: Returning '{uid}'")
        return uid


class NecTemperatureSensor(NecSensor):
    """Representation of a NEC temperature sensor."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_name = "Temperature"

    def __init__(self, coordinator, config_entry):
        """Initialize the temperature sensor."""
        super().__init__(coordinator, config_entry)
        # Initial state can be fetched from coordinator.data if ready at init
        if "temperature" in coordinator.data:
            self._attr_native_value = coordinator.data["temperature"]
        else:
            self._attr_native_value = None
        self._attr_available = coordinator.last_update_success

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        try:
            await self.coordinator.async_request_refresh()
            if "temperature" in self.coordinator.data:
                self._attr_native_value = self.coordinator.data["temperature"]
                self._attr_available = True
            else:
                self._attr_available = False
                _LOGGER.warning(
                    "Temperature data not available during update."
                )
        except Exception as e:
            _LOGGER.error(f"Error updating temperature sensor: {e}")
            self._attr_available = False


class NecLampHoursSensor(NecSensor):
    """Representation of a NEC lamp hours sensor."""

    _attr_native_unit_of_measurement = "hours"
    _attr_name = "Lamp Hours"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config_entry):
        """Initialize the lamp hours sensor."""
        super().__init__(coordinator, config_entry)
        # Initial state can be fetched from coordinator.data if available at init
        if "lamp_hours" in coordinator.data:
            self._attr_native_value = coordinator.data["lamp_hours"]
        else:
            self._attr_native_value = None
        self._attr_available = coordinator.last_update_success

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        try:
            await self.coordinator.async_request_refresh()
            if "lamp_hours" in self.coordinator.data:
                self._attr_native_value = self.coordinator.data["lamp_hours"]
                self._attr_available = True
            else:
                self._attr_available = False
                _LOGGER.warning("Lamp hours data not available during update.")
        except Exception as e:
            _LOGGER.error(f"Error updating lamp hours sensor: {e}")
            self._attr_available = False
