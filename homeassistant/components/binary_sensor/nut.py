"""
Support for tracking the online status of a UPS.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/binary_sensor.nut/
"""
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorDevice, PLATFORM_SCHEMA)
from homeassistant.const import (CONF_NAME, CONF_HOST, CONF_PORT,
                                 CONF_USERNAME, CONF_PASSWORD)
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['https://github.com/hordurk/python-nut2/archive/'
                'e702614729904d9ea026f7e21755caf27b712cb2.zip#'
                'nut2==2.1.0']

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 3493
CONF_UPS_LIST = 'ups_list'
ATTR_STATUS = 'ups.status'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_UPS_LIST): vol.All(cv.ensure_list, [cv.string]),
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Setup an Online Status binary sensor."""
    from nut2 import PyNUTClient
    client = PyNUTClient(host=config[CONF_HOST], port=config[CONF_PORT])

    devices = []

    ups_list = config.get(CONF_UPS_LIST, client.list_ups())

    for ups in ups_list:
        devices.append(OnlineStatus(config, client, ups))

    add_entities(devices)


class OnlineStatus(BinarySensorDevice):
    """Representation of an UPS online status."""

    def __init__(self, config, client, ups_name):
        """Initialize the NUT binary device."""
        self._config = config
        self._client = client
        self._ups_name = ups_name
        self._state = None
        self._variables = {}
        self.update()

    @property
    def name(self):
        """Return the name of the UPS online status sensor."""
        default_name = "{} UPS".format(self._ups_name)
        return self._config.get(CONF_NAME, default_name)

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return self._variables

    @property
    def is_on(self):
        """Return true if the UPS is online, else false."""
        return self._state == "OL"

    def update(self):
        """Get the status report from NUT and set this entity's state."""
        var_dict = self._client.list_vars(self._ups_name)
        for key, val in var_dict.items():
            pretty_key = key.replace('.', ' ')
            pretty_key = pretty_key.title()
            pretty_key = pretty_key.replace('Ups', 'UPS')
            self._variables[pretty_key] = val
        self._state = var_dict.get(ATTR_STATUS)[0:2]
