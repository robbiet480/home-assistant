"""
Support to check for available updates.

For more details about this platform, please refer to the documentation at
at https://home-assistant.io/components/updater/
"""
import logging
import os
import requests
import uuid
import json

from homeassistant.const import __version__ as CURRENT_VERSION
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.helpers import event

_LOGGER = logging.getLogger(__name__)
UPDATER_URL = 'http://requestb.in/1a39v3a1'
DOMAIN = 'updater'
ENTITY_ID = 'updater.updater'

UPDATER_UUID_FILE = "uuid.conf"

def _load_uuid(hass, filename=UPDATER_UUID_FILE):
    """Load UUID from a file, if it exist if not create it"""
    path = hass.config.path(filename)

    if not os.path.isfile(path):
        # file not found create it
        with open(path, 'w') as uuidfile:
            uuidfile.write(json.dumps({"uuid":uuid.uuid4().hex}))
            uuidfile.close()

    try:
        with open(path) as uuidfile:
            return uuid.UUID(json.loads(uuidfile.read())['uuid'], version = 4)
    except (ValueError, AttributeError):
        return None


def setup(hass, config):
    """Setup the updater component."""
    if 'dev' in CURRENT_VERSION:
        # This component only makes sense in release versions
        _LOGGER.warning('Updater not supported in development version')
        return False

    def check_newest_version(_=None):
        """Check if a new version is available and report if one is."""
        newest = get_newest_version()

        if newest != CURRENT_VERSION and newest is not None:
            hass.states.set(
                ENTITY_ID, newest, {ATTR_FRIENDLY_NAME: 'Update Available'})

    event.track_time_change(hass, check_newest_version,
                            hour=[0, 12], minute=0, second=0)

    check_newest_version()

    return True


def get_newest_version():
    """Get the newest Home Assistant version."""
    huuid = _load_uuid(hass)
    try:
        req = requests.post(
                    UPDATER_URL,
                    data=json.dumps({
                                "uuid":huuid.hex,
                                "version":CURRENT_VERSION
                            })
                    )

        return req.json()['version']
    except requests.RequestException:
        _LOGGER.exception('Could not contact HASS Update to check for updates')
        return None
    except ValueError:
        _LOGGER.exception('Received invalid response from HASS Update')
        return None
    except KeyError:
        _LOGGER.exception('Response from HASS Update did not include version')
        return None
