"""
Socket.io for Home Assistant.

For more details about Socket.io, please refer to the documentation at
https://home-assistant.io/components/socketio/
"""
import json
import logging

# import homeassistant.core as ha
import homeassistant.remote as rem
# from homeassistant.bootstrap import ERROR_LOG_FILENAME
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP, EVENT_TIME_CHANGED,
    HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_NOT_FOUND,
    HTTP_UNPROCESSABLE_ENTITY, MATCH_ALL, URL_API, URL_API_COMPONENTS,
    URL_API_CONFIG, URL_API_DISCOVERY_INFO, URL_API_ERROR_LOG,
    URL_API_EVENT_FORWARD, URL_API_EVENTS, URL_API_SERVICES,
    URL_API_STATES, URL_API_STATES_ENTITY, URL_API_STREAM, URL_API_TEMPLATE,
    __version__)
# from homeassistant.exceptions import TemplateError
# from homeassistant.helpers.state import TrackStates
# from homeassistant.helpers import template
# from homeassistant.components.http import HomeAssistantView

DOMAIN = 'socketio'
DEPENDENCIES = ['http']
REQUIREMENTS = ['python-socketio==1.3']

_LOGGER = logging.getLogger(__name__)


def setup(hass, config):
    """Setup Socket.io server."""
    import socketio
    sio = socketio.Server(async_mode='eventlet')

    stop_obj = object()

    def thread_forward_events(event):
        """Forward events to the open request."""
        if event.event_type == EVENT_TIME_CHANGED:
            return

        _LOGGER.debug('STREAM %s FORWARDING %s', id(stop_obj), event)

        if event.event_type == EVENT_HOMEASSISTANT_STOP:
            data = stop_obj
        else:
            data = json.dumps(event, cls=rem.JSONEncoder)

        sio.emit(event.event_type, data=data, room=event.event_type)
        sio.emit(event.event_type, data=data)

    @sio.on('connect')
    # pylint: disable=unused-variable
    def connect(sid, environ):
        """Handle Socket.io connection events."""
        print('connect', sid)
        hass.bus.listen(MATCH_ALL, thread_forward_events)

    @sio.on('disconnect')
    # pylint: disable=unused-variable
    def disconnect(sid):
        """Handle Socket.io disconnection events."""
        print('disconnect ', sid)

    def socketio_mw(app):
        """Build Socket.io middleware."""
        return socketio.Middleware(sio, app)

    hass.wsgi.register_wsgi_middleware(socketio_mw)

    return True
