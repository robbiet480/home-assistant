"""Support for alexa Smart Home Skill API."""
import asyncio
import logging
import math
from uuid import uuid4

from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES, ATTR_ENTITY_ID, SERVICE_TURN_ON,
    SERVICE_TURN_OFF, SERVICE_LOCK, SERVICE_UNLOCK, SERVICE_VOLUME_SET)
from homeassistant.components import (
    fan, input_boolean, light, lock, media_player, scene, script, switch)
import homeassistant.util.color as color_util
from homeassistant.util.decorator import Registry

HANDLERS = Registry()
_LOGGER = logging.getLogger(__name__)

API_DIRECTIVE = 'directive'
API_EVENT = 'event'
API_HEADER = 'header'
API_PAYLOAD = 'payload'
API_ENDPOINT = 'endpoint'

ATTR_ALEXA_HIDDEN = 'alexa_hidden'
ATTR_ALEXA_NAME = 'alexa_name'
ATTR_ALEXA_DESCRIPTION = 'alexa_description'
ATTR_ALEXA_MEDIA_CATEGORY = 'alexa_media_category'


MAPPING_COMPONENT = {
    fan.DOMAIN: [
        'SWITCH', ('Alexa.PowerController',), {
            fan.SUPPORT_SET_SPEED: 'Alexa.PercentageController',
        }
    ],
    input_boolean.DOMAIN: ['SWITCH', ('Alexa.PowerController',), None],
    light.DOMAIN: [
        'LIGHT', ('Alexa.PowerController',), {
            light.SUPPORT_BRIGHTNESS: 'Alexa.BrightnessController',
            light.SUPPORT_RGB_COLOR: 'Alexa.ColorController',
            light.SUPPORT_XY_COLOR: 'Alexa.ColorController',
            light.SUPPORT_COLOR_TEMP: 'Alexa.ColorTemperatureController',
        }
    ],
    lock.DOMAIN: ['SMARTLOCK', ('Alexa.LockController',), None],
    media_player.DOMAIN: [
        'TV', ('Alexa.PowerController',), {
            media_player.SUPPORT_VOLUME_SET: 'Alexa.Speaker',
        }
    ],
    scene.DOMAIN: ['ACTIVITY_TRIGGER', ('Alexa.SceneController',), None],
    script.DOMAIN: ['SWITCH', ('Alexa.PowerController',), None],
    switch.DOMAIN: ['SWITCH', ('Alexa.PowerController',), None],
}


@asyncio.coroutine
def async_handle_message(hass, message):
    """Handle incoming API messages."""
    assert message[API_DIRECTIVE][API_HEADER]['payloadVersion'] == '3'

    # Read head data
    message = message[API_DIRECTIVE]
    namespace = message[API_HEADER]['namespace']
    name = message[API_HEADER]['name']

    # Do we support this API request?
    funct_ref = HANDLERS.get((namespace, name))
    if not funct_ref:
        _LOGGER.warning(
            "Unsupported API request %s/%s", namespace, name)
        return api_error(message)

    return (yield from funct_ref(hass, message))


def api_message(request, name='Response', namespace='Alexa', payload=None):
    """Create a API formatted response message.

    Async friendly.
    """
    payload = payload or {}

    response = {
        API_EVENT: {
            API_HEADER: {
                'namespace': namespace,
                'name': name,
                'messageId': str(uuid4()),
                'payloadVersion': '3',
            },
            API_PAYLOAD: payload,
        }
    }

    # If a correlation token exsits, add it to header / Need by Async requests
    token = request[API_HEADER].get('correlationToken')
    if token:
        response[API_EVENT][API_HEADER]['correlationToken'] = token

    # Extend event with endpoint object / Need by Async requests
    if API_ENDPOINT in request:
        response[API_EVENT][API_ENDPOINT] = request[API_ENDPOINT].copy()

    return response


def api_error(request, error_type='INTERNAL_ERROR', error_message=""):
    """Create a API formatted error response.

    Async friendly.
    """
    payload = {
        'type': error_type,
        'message': error_message,
    }

    return api_message(request, name='ErrorResponse', payload=payload)


@HANDLERS.register(('Alexa.Discovery', 'Discover'))
@asyncio.coroutine
def async_api_discovery(hass, request):
    """Create a API formatted discovery response.

    Async friendly.
    """
    discovery_endpoints = []

    for entity in hass.states.async_all():
        if entity.attributes.get(ATTR_ALEXA_HIDDEN, False):
            continue

        class_data = MAPPING_COMPONENT.get(entity.domain)

        if not class_data:
            continue

        friendly_name = entity.attributes.get(ATTR_ALEXA_NAME, entity.name)
        description = entity.attributes.get(ATTR_ALEXA_DESCRIPTION,
                                            entity.entity_id)

        display_categories = class_data[0]
        if entity.domain == media_player.DOMAIN:
            cat_key = ATTR_ALEXA_MEDIA_CATEGORY
            display_categories = entity.attributes.get(cat_key, 'TV')

        endpoint = {
            'displayCategories': [display_categories],
            'additionalApplianceDetails': {},
            'endpointId': entity.entity_id.replace('.', '#'),
            'friendlyName': friendly_name,
            'description': description,
            'manufacturerName': 'Unknown',
        }
        actions = set()

        # static actions
        if class_data[1]:
            actions |= set(class_data[1])

        # dynamic actions
        if class_data[2]:
            supported = entity.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            for feature, action_name in class_data[2].items():
                if feature & supported > 0:
                    actions.add(action_name)

        # Write action into capabilities
        capabilities = []
        for action in actions:
            capabilities.append({
                'type': 'AlexaInterface',
                'interface': action,
                'version': 3,
            })

        endpoint['capabilities'] = capabilities
        discovery_endpoints.append(endpoint)

    return api_message(
        request, name='Discover.Response', namespace='Alexa.Discovery',
        payload={'endpoints': discovery_endpoints})


def extract_entity(funct):
    """Decorator for extract entity object from request."""
    @asyncio.coroutine
    def async_api_entity_wrapper(hass, request):
        """Process a turn on request."""
        entity_id = request[API_ENDPOINT]['endpointId'].replace('#', '.')

        # extract state object
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.error("Can't process %s for %s",
                          request[API_HEADER]['name'], entity_id)
            return api_error(request, error_type='NO_SUCH_ENDPOINT')

        return (yield from funct(hass, request, entity))

    return async_api_entity_wrapper


@HANDLERS.register(('Alexa.PowerController', 'TurnOn'))
@extract_entity
@asyncio.coroutine
def async_api_turn_on(hass, request, entity):
    """Process a turn on request."""
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.PowerController', 'TurnOff'))
@extract_entity
@asyncio.coroutine
def async_api_turn_off(hass, request, entity):
    """Process a turn off request."""
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_OFF, {
        ATTR_ENTITY_ID: entity.entity_id
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.BrightnessController', 'SetBrightness'))
@extract_entity
@asyncio.coroutine
def async_api_set_brightness(hass, request, entity):
    """Process a set brightness request."""
    brightness = int(request[API_PAYLOAD]['brightness'])

    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id,
        light.ATTR_BRIGHTNESS_PCT: brightness,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.BrightnessController', 'AdjustBrightness'))
@extract_entity
@asyncio.coroutine
def async_api_adjust_brightness(hass, request, entity):
    """Process a adjust brightness request."""
    brightness_delta = int(request[API_PAYLOAD]['brightnessDelta'])

    # read current state
    try:
        current = math.floor(
            int(entity.attributes.get(light.ATTR_BRIGHTNESS)) / 255 * 100)
    except ZeroDivisionError:
        current = 0

    # set brightness
    brightness = max(0, brightness_delta + current)
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id,
        light.ATTR_BRIGHTNESS_PCT: brightness,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.ColorController', 'SetColor'))
@extract_entity
@asyncio.coroutine
def async_api_set_color(hass, request, entity):
    """Process a set color request."""
    supported = entity.attributes.get(ATTR_SUPPORTED_FEATURES)
    rgb = color_util.color_hsb_to_RGB(
        float(request[API_PAYLOAD]['color']['hue']),
        float(request[API_PAYLOAD]['color']['saturation']),
        float(request[API_PAYLOAD]['color']['brightness'])
    )

    if supported & light.SUPPORT_RGB_COLOR > 0:
        yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
            ATTR_ENTITY_ID: entity.entity_id,
            light.ATTR_RGB_COLOR: rgb,
        }, blocking=True)
    else:
        xyz = color_util.color_RGB_to_xy(*rgb)
        yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
            ATTR_ENTITY_ID: entity.entity_id,
            light.ATTR_XY_COLOR: (xyz[0], xyz[1]),
            light.ATTR_BRIGHTNESS: xyz[2],
        }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.ColorTemperatureController', 'SetColorTemperature'))
@extract_entity
@asyncio.coroutine
def async_api_set_color_temperature(hass, request, entity):
    """Process a set color temperature request."""
    kelvin = int(request[API_PAYLOAD]['colorTemperatureInKelvin'])

    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id,
        light.ATTR_KELVIN: kelvin,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(
    ('Alexa.ColorTemperatureController', 'DecreaseColorTemperature'))
@extract_entity
@asyncio.coroutine
def async_api_decrease_color_temp(hass, request, entity):
    """Process a decrease color temperature request."""
    current = int(entity.attributes.get(light.ATTR_COLOR_TEMP))
    max_mireds = int(entity.attributes.get(light.ATTR_MAX_MIREDS))

    value = min(max_mireds, current + 50)
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id,
        light.ATTR_COLOR_TEMP: value,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(
    ('Alexa.ColorTemperatureController', 'IncreaseColorTemperature'))
@extract_entity
@asyncio.coroutine
def async_api_increase_color_temp(hass, request, entity):
    """Process a increase color temperature request."""
    current = int(entity.attributes.get(light.ATTR_COLOR_TEMP))
    min_mireds = int(entity.attributes.get(light.ATTR_MIN_MIREDS))

    value = max(min_mireds, current - 50)
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id,
        light.ATTR_COLOR_TEMP: value,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.SceneController', 'Activate'))
@extract_entity
@asyncio.coroutine
def async_api_activate(hass, request, entity):
    """Process a activate request."""
    yield from hass.services.async_call(entity.domain, SERVICE_TURN_ON, {
        ATTR_ENTITY_ID: entity.entity_id
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.PercentageController', 'SetPercentage'))
@extract_entity
@asyncio.coroutine
def async_api_set_percentage(hass, request, entity):
    """Process a set percentage request."""
    percentage = int(request[API_PAYLOAD]['percentage'])
    speed = "off"

    if percentage <= 33:
        speed = "low"
    elif percentage <= 66:
        speed = "medium"
    elif percentage <= 100:
        speed = "high"

    yield from hass.services.async_call(entity.domain, fan.SERVICE_SET_SPEED, {
        ATTR_ENTITY_ID: entity.entity_id,
        fan.ATTR_SPEED: speed,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.PercentageController', 'AdjustPercentage'))
@extract_entity
@asyncio.coroutine
def async_api_adjust_percentage(hass, request, entity):
    """Process a adjust percentage request."""
    percentage_delta = int(request[API_PAYLOAD]['percentageDelta'])
    speed = entity.attributes.get(fan.ATTR_SPEED)

    if speed == "off":
        current = 0
    elif speed == "low":
        current = 33
    elif speed == "medium":
        current = 66
    elif speed == "high":
        current = 100

    # set percentage
    percentage = max(0, percentage_delta + current)
    speed = "off"

    if percentage <= 33:
        speed = "low"
    elif percentage <= 66:
        speed = "medium"
    elif percentage <= 100:
        speed = "high"
    yield from hass.services.async_call(entity.domain, fan.SERVICE_SET_SPEED, {
        ATTR_ENTITY_ID: entity.entity_id,
        fan.ATTR_SPEED: speed,
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.LockController', 'Lock'))
@extract_entity
@asyncio.coroutine
def async_api_lock(hass, request, entity):
    """Process a lock request."""
    yield from hass.services.async_call(entity.domain, SERVICE_LOCK, {
        ATTR_ENTITY_ID: entity.entity_id
    }, blocking=True)

    return api_message(request)


# Not supported by Alexa yet
@HANDLERS.register(('Alexa.LockController', 'Unlock'))
@extract_entity
@asyncio.coroutine
def async_api_unlock(hass, request, entity):
    """Process a unlock request."""
    yield from hass.services.async_call(entity.domain, SERVICE_UNLOCK, {
        ATTR_ENTITY_ID: entity.entity_id
    }, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.Speaker', 'SetVolume'))
@extract_entity
@asyncio.coroutine
def async_api_set_volume(hass, request, entity):
    """Process a set volume request."""
    volume = float(request[API_PAYLOAD]['volume'] * 100)

    data = {
        ATTR_ENTITY_ID: entity.entity_id,
        media_player.ATTR_MEDIA_VOLUME_LEVEL: volume,
    }

    yield from hass.services.async_call(entity.domain,
                                        media_player.SERVICE_VOLUME_SET,
                                        data, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.Speaker', 'AdjustVolume'))
@extract_entity
@asyncio.coroutine
def async_api_adjust_volume(hass, request, entity):
    """Process a adjust volume request."""
    volume_delta = float(request[API_PAYLOAD]['volume'])

    current_level = entity.attributes.get(media_player.ATTR_MEDIA_VOLUME_LEVEL)

    # read current state
    try:
        current = math.floor(float(current_level) * 100)
    except ZeroDivisionError:
        current = 0

    volume = max(0, volume_delta + current)

    data = {
        ATTR_ENTITY_ID: entity.entity_id,
        media_player.ATTR_MEDIA_VOLUME_LEVEL: volume,
    }

    yield from hass.services.async_call(entity.domain,
                                        media_player.SERVICE_VOLUME_SET,
                                        data, blocking=True)

    return api_message(request)


@HANDLERS.register(('Alexa.Speaker', 'SetMute'))
@extract_entity
@asyncio.coroutine
def async_api_set_mute(hass, request, entity):
    """Process a set mute request."""
    mute = bool(request[API_PAYLOAD]['mute'])

    data = {
        ATTR_ENTITY_ID: entity.entity_id,
        media_player.ATTR_MEDIA_VOLUME_MUTED: mute,
    }

    yield from hass.services.async_call(entity.domain,
                                        media_player.SERVICE_VOLUME_MUTE,
                                        data, blocking=True)

    return api_message(request)
