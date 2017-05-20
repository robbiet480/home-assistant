"""
Support for hass.io DynDNS registration and updating.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/dyndns/
"""

import logging
import asyncio
import json
import datetime
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'dyndns'

_CONFIGURING = {}

CONF_DOMAIN_NAME = 'domain_name'

BASE_URL = 'https://bkujetwt7d.execute-api.us-west-2.amazonaws.com/Production/'
STATUS_URL = '{}record/change_status'.format(BASE_URL)
TXT_URL = '{}record/txt_record'.format(BASE_URL)
REGISTER_URL = '{}record/update'.format(BASE_URL)
IPV6_URL = 'http://v6.ipv6-test.com/api/myip.php?json'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_DOMAIN_NAME): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)


@asyncio.coroutine
def async_setup(hass, config):
    """Set up the DynDNS component."""
    websession = async_get_clientsession(hass)

    domain_name = config[DOMAIN][CONF_DOMAIN_NAME]

    @asyncio.coroutine
    def update_dyndns(now):
        """Update DynDNS record(s)."""
        yield from update_record(websession, domain_name)

    _dt = dt_util.utcnow() + datetime.timedelta(hours=1)

    yield from update_dyndns(0)

    event.async_track_utc_time_change(hass, update_dyndns, hour=_dt.hour,
                                      minute=_dt.minute, second=_dt.second)

    return True


async def update_record(websession, subdomain):
    """Register the subdomain."""
    payload = {'subdomain': subdomain}
    # AWS API Gateway doesn't support IPv6 yet, so client needs to provide it.
    try:
        resp = await websession.get(IPV6_URL)
        resp_body = await resp.text()
        json_body = json.loads(resp_body)
        payload['ipv6'] = json_body['address']
    except OSError as err:
        if err.errno == 65:
            _LOGGER.warning("You don't have an IPv6 address, continuing!")
        else:
            msg = 'Error encountered when attempting to determine IPv6 address'
            _LOGGER.error(msg, err)

    async with websession.post(REGISTER_URL,
                               data=json.dumps(payload)) as resp:
        _LOGGER.info('Registered!')
