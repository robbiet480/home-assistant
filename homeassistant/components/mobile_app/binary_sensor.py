"""Binary sensor platform for mobile_app."""
from homeassistant.components.binary_sensor import BinarySensorDevice
from homeassistant.const import CONF_WEBHOOK_ID

from .const import (ATTR_SENSOR_STATE, ATTR_SENSOR_TYPE_BINARY_SENSOR,
                    ATTR_SENSOR_UNIQUE_ID, DATA_BINARY_SENSOR,
                    DATA_REGISTRATIONS, DOMAIN)

from .entity import MobileAppEntity

DEPENDENCIES = ['mobile_app']


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the mobile app binary sensor."""
    devices = hass.data[DOMAIN][DATA_REGISTRATIONS]
    sensor_configs = hass.data[DOMAIN][DATA_BINARY_SENSOR]

    devs = list()

    if discovery_info is None:
        for sensor_config in sensor_configs.values():
            device = devices[sensor_config[CONF_WEBHOOK_ID]]
            devs.append(MobileAppBinarySensor(sensor_config, device))
    else:
        device = devices[discovery_info[CONF_WEBHOOK_ID]]
        sensor_config = sensor_configs[discovery_info[ATTR_SENSOR_UNIQUE_ID]]
        devs.append(MobileAppBinarySensor(sensor_config, device))

    async_add_entities(devs, True)


class MobileAppBinarySensor(MobileAppEntity, BinarySensorDevice):
    """Representation of an mobile app binary sensor."""

    def __init__(self, config, device):
        """Initialize the binary sensor."""
        super().__init__(ATTR_SENSOR_TYPE_BINARY_SENSOR, config, device)

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        return self._config[ATTR_SENSOR_STATE]
