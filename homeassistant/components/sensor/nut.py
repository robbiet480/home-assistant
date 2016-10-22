"""
Provides a sensor to track various status aspects of a UPS.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.apcupsd/
"""
import logging

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_NAME, CONF_HOST, CONF_PORT,
                                 CONF_USERNAME, CONF_PASSWORD,
                                 TEMP_CELSIUS, CONF_MONITORED_VARIABLES)
from homeassistant.helpers.entity import Entity

REQUIREMENTS = ['https://github.com/hordurk/python-nut2/archive/'
                'e702614729904d9ea026f7e21755caf27b712cb2.zip#'
                'nut2==2.1.0']

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 3493
CONF_UPS_LIST = 'ups_list'
ATTR_STATUS = 'ups.status'

SENSOR_TYPES = {
    'battery.alarm.threshold': ['Alarm Delay', '', 'mdi:alarm'],
    'battery.charge': ['Battery', '%', 'mdi:battery'],
    'battery.charge.low': ['Battery Shutdown', '%', 'mdi:battery-alert'],
    'battery.charge.restart': ['Restore Requirement', '%',
                               'mdi:battery-alert'],
    'battery.charger.status': ['Battery Status', '',
                               'mdi:information-outline'],
    'battery.date': ['Battery Replaced', '', 'mdi:calendar-clock'],
    'battery.packs': ['External Batteries', '', 'mdi:information-outline'],
    'battery.packs.bad': ['Bad Batteries', '', 'mdi:information-outline'],
    # 'battery.runtime': ['Battery Timeout', '', 'mdi:timer-off'],
    'battery.runtime': ['Time Left', '', 'mdi:clock-alert'],
    'battery.runtime.low': ['Low Battery Signal', '', 'mdi:clock-alert'],
    'battery.voltage': ['Battery Voltage', 'V', 'mdi:flash'],
    'battery.voltage.nominal': ['Battery Nominal Voltage', 'V', 'mdi:flash'],
    'device.model': ['Model', '', 'mdi:information-outline'],
    'driver.name': ['Driver', '', 'mdi:information-outline'],
    'driver.version': ['Daemon Info', '', 'mdi:information-outline'],
    'input.frequency': ['Line Frequency', 'Hz', 'mdi:information-outline'],
    'input.sensitivity': ['Sensitivity', '', 'mdi:information-outline'],
    'input.transfer.high': ['Transfer High', 'V', 'mdi:flash'],
    'input.transfer.low': ['Transfer Low', 'V', 'mdi:flash'],
    'input.transfer.reason': ['Last Transfer', '', 'mdi:transfer'],
    'input.voltage': ['Input Voltage', 'V', 'mdi:flash'],
    'input.voltage.maximum': ['Input Voltage High', 'V', 'mdi:flash'],
    'input.voltage.minimum': ['Input Voltage Low', 'V', 'mdi:flash'],
    'input.voltage.nominal': ['Nominal Input Voltage', 'V', 'mdi:flash'],
    'input.voltage.status': ['Input Voltage Status', '',
                             'mdi:information-outline'],
    'output.voltage': ['Output Voltage', 'V', 'mdi:flash'],
    'output.voltage.nominal': ['Nominal Output Voltage', 'V', 'mdi:flash'],
    'ups.date': ['Status Date', '', 'mdi:calendar-clock'],
    'ups.delay.shutdown': ['Shutdown Delay', '', 'mdi:timer'],
    'ups.delay.start': ['Wake Delay', '', 'mdi:timer'],
    'ups.firmware': ['Firmware Version', '', 'mdi:information-outline'],
    'ups.id': ['Name', '', 'mdi:information-outline'],
    'ups.load': ['Load', '%', 'mdi:gauge'],
    'ups.mfr.date': ['Manufacture Date', '', 'mdi:calendar'],
    'ups.model': ['Model', '', 'mdi:information-outline'],
    'ups.realpower.nominal': ['Nominal Output Power', 'W', 'mdi:flash'],
    'ups.serial': ['Serial Number', '', 'mdi:information-outline'],
    'ups.status': ['Status', '', 'mdi:information-outline'],
    'ups.temperature': ['Internal Temperature', TEMP_CELSIUS,
                        'mdi:thermometer'],
    'ups.test.interval': ['Self Test Interval', '',
                          'mdi:information-outline'],
    'ups.test.result': ['Last Self Test', '', 'mdi:calendar-clock'],
    'ups.time': ['Date and Time', '', 'mdi:calendar-clock'],
    'ups.timer.shutdown': ['Shutdown Time', '', 'mdi:timer'],
}

INFERRED_UNITS = {
    ' Minutes': 'min',
    ' Seconds': 'sec',
    ' Percent': '%',
    ' Volts': 'V',
    ' Watts': 'W',
    ' Hz': 'Hz',
    ' C': TEMP_CELSIUS,
}

UPS_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_MONITORED_VARIABLES):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_UPS_LIST): vol.All(cv.ensure_list, [UPS_SCHEMA]),
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Setup the NUT sensors."""

    from nut2 import PyNUTClient
    client = PyNUTClient(host=config[CONF_HOST], port=config[CONF_PORT])

    entities = []

    ups_list = config.get(CONF_UPS_LIST, client.list_ups())

    for ups_name in ups_list:
        ups_variables = client.list_vars(ups_name)
        for sensor_type in config.get(CONF_MONITORED_VARIABLES, ups_variables):
            if sensor_type not in SENSOR_TYPES:
                pretty_key = sensor_type.replace('.', ' ')
                pretty_key = pretty_key.title()
                pretty_key = pretty_key.replace('Ups', 'UPS')
                SENSOR_TYPES[sensor_type] = [
                    pretty_key, '', 'mdi:information-outline']

            if sensor_type not in ups_variables:
                _LOGGER.warning(
                    'Sensor type: "%s" does not appear in the NUT status '
                    'output', sensor_type)
                continue

            entities.append(NUTSensor(client, ups_name, sensor_type))

    add_entities(entities)


class NUTSensor(Entity):
    """Representation of a sensor entity for NUT status values."""

    def __init__(self, client, ups_name, sensor_type):
        """Initialize the sensor."""
        self._client = client
        self._ups_name = ups_name
        self.type = sensor_type
        self._name = ups_name + SENSOR_TYPES[sensor_type][0]
        self._unit = SENSOR_TYPES[sensor_type][1]
        self.update()

    @property
    def name(self):
        """Return the name of the UPS sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return SENSOR_TYPES[self.type][2]

    @property
    def state(self):
        """Return true if the UPS is online, else False."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    def update(self):
        """Get the latest status and use it to update our sensor state."""
        from nut2 import PyNUTError
        try:
            self._state = self._client.get_var(self._ups_name, self.type)
        except PyNUTError as exc:
            if str(exc) == "ERR VAR-NOT-SUPPORTED":
                _LOGGER.error('Sensor type: "%s" is not a valid variable',
                              self.type)
                self._state = None
            else:
                _LOGGER.error(exc)
