"""A entity class for mobile_app."""
import logging

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (ATTR_SENSOR_ATTRIBUTES,
                    ATTR_SENSOR_DEVICE_CLASS, ATTR_SENSOR_ICON,
                    ATTR_SENSOR_NAME, ATTR_SENSOR_TYPE, ATTR_SENSOR_UNIQUE_ID,
                    DATA_REGISTRATIONS, DOMAIN, SIGNAL_SENSOR_UPDATE)

_LOGGER = logging.getLogger(__name__)


class MobileAppEntity(Entity):
    """Representation of an mobile app entity."""

    def __init__(self, entity_type, config, device):
        """Initialize the sensor."""
        self._config = config
        self._device = device
        self._device_id = device[CONF_WEBHOOK_ID]
        self._sensor_id = config[ATTR_SENSOR_UNIQUE_ID]
        self._entity_type = config[ATTR_SENSOR_TYPE]

    async def async_added_to_hass(self):
        """Register callbacks."""
        async_dispatcher_connect(self.hass, SIGNAL_SENSOR_UPDATE,
                                 self._handle_update)

    async def async_will_remove_from_hass(self):
        """Disconnect dispatcher listener when removed."""
        async_dispatcher_connect(self.hass, SIGNAL_SENSOR_UPDATE,
                                 self._handle_update)

    @property
    def should_poll(self) -> bool:
        """Declare that this entity pushes its state to HA."""
        return False

    @property
    def name(self):
        """Return the name of the mobile app sensor."""
        return self._config[ATTR_SENSOR_NAME]

    @property
    def device_class(self):
        """Return the device class."""
        return self._config.get(ATTR_SENSOR_DEVICE_CLASS)

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return self._config[ATTR_SENSOR_ATTRIBUTES]

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._config[ATTR_SENSOR_ICON]

    @property
    def unique_id(self):
        """Return the unique ID of this sensor."""
        return self._sensor_id

    async def async_update(self):
        """Get the latest state of the sensor."""
        data = self.hass.data[DOMAIN]
        self._device = data[DATA_REGISTRATIONS][self._device_id]
        self._config = data[self._entity_type][self._sensor_id]

    @callback
    def _handle_update(self, data):
        """Handle async event updates."""
        self._config = data
        self.async_schedule_update_ha_state()
