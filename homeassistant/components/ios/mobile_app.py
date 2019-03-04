"""iOS app specific logic."""
import logging
from aiohttp.web import json_response

from homeassistant.helpers import template

from . import CONF_PUSH, DOMAIN

_LOGGER = logging.getLogger(__name__)

WEBHOOK_TYPE_GET_PUSH_CONFIG = 'get_push_config'
WEBHOOK_TYPE_RENDER_COMPLICATIONS = 'render_complications'

WEBHOOK_TYPES = [WEBHOOK_TYPE_GET_PUSH_CONFIG,
                 WEBHOOK_TYPE_RENDER_COMPLICATIONS]


async def async_handle_webhook_message(hass, device, webhook_type, data):
    """Return a webhook response for the given arguments."""
    _LOGGER.debug("iOS: received webhook %s %s %s", webhook_type, device,
                  data)

    if webhook_type == WEBHOOK_TYPE_GET_PUSH_CONFIG:
        return json_response(hass.data[DOMAIN][CONF_PUSH])

    if webhook_type == WEBHOOK_TYPE_RENDER_COMPLICATIONS:
        resp = {}
        for family, templates in data['templates'].items():
            resp[family] = {}
            for key, tpl in templates.items():
                rendered = template.Template(tpl, hass).async_render()
                resp[family][key] = rendered
        return json_response(resp)
