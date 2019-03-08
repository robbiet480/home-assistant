"""Sensor platform for mobile_app."""
from homeassistant.const import CONF_WEBHOOK_ID

from .const import (ATTR_SENSOR_STATE,
                    ATTR_SENSOR_TYPE_SENSOR, ATTR_SENSOR_UNIQUE_ID,
                    ATTR_SENSOR_UOM, DATA_REGISTRATIONS, DATA_SENSOR, DOMAIN)

from .entity import MobileAppEntity

DEPENDENCIES = ['mobile_app']


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the mobile app sensor."""
    devices = hass.data[DOMAIN][DATA_REGISTRATIONS]
    sensor_configs = hass.data[DOMAIN][DATA_SENSOR]

    devs = list()

    if discovery_info is None:
        for sensor_config in sensor_configs.values():
            device = devices[sensor_config[CONF_WEBHOOK_ID]]
            devs.append(MobileAppSensor(sensor_config, device))
    else:
        device = devices[discovery_info[CONF_WEBHOOK_ID]]
        sensor_config = sensor_configs[discovery_info[ATTR_SENSOR_UNIQUE_ID]]
        devs.append(MobileAppSensor(sensor_config, device))

    async_add_entities(devs, True)


class MobileAppSensor(MobileAppEntity):
    """Representation of an mobile app sensor."""

    def __init__(self, config, device):
        """Initialize the sensor."""
        super().__init__(ATTR_SENSOR_TYPE_SENSOR, config, device)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._config[ATTR_SENSOR_STATE]

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._config[ATTR_SENSOR_UOM]
