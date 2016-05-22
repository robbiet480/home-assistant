"""
Rest API for Home Assistant.

For more details about the RESTful API, please refer to the documentation at
https://home-assistant.io/developers/api/
"""
import json
import logging

# import homeassistant.core as ha
# import homeassistant.remote as rem
# from homeassistant.bootstrap import ERROR_LOG_FILENAME
# from homeassistant.const import (
#     EVENT_HOMEASSISTANT_STOP, EVENT_TIME_CHANGED,
#     HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_NOT_FOUND,
#     HTTP_UNPROCESSABLE_ENTITY, MATCH_ALL, URL_API, URL_API_COMPONENTS,
#     URL_API_CONFIG, URL_API_DISCOVERY_INFO, URL_API_ERROR_LOG,
#     URL_API_EVENT_FORWARD, URL_API_EVENTS, URL_API_SERVICES,
#     URL_API_STATES, URL_API_STATES_ENTITY, URL_API_STREAM, URL_API_TEMPLATE,
#     __version__)
# from homeassistant.exceptions import TemplateError
# from homeassistant.helpers.state import TrackStates
# from homeassistant.helpers import template
# from homeassistant.components.http import HomeAssistantView

DOMAIN = 'socketio'
DEPENDENCIES = ['http']
REQUIREMENTS = ['python-socketio==1.3']

_LOGGER = logging.getLogger(__name__)

def setup(hass, config):

  import socketio
  sio = socketio.Server(async_mode='eventlet')
  # sio = socketio.Server(async_mode='eventlet', cors_allowed_origins=['localhost:9010'], cors_credentials=False)

  @sio.on('connect')
  def connect(sid, environ):
      environ['eventlet.minimum_write_chunk_size'] = 0
      print('connect ', sid)

  @sio.on('my message')
  def message(sid, data):
      print('message ', data)

  @sio.on('disconnect')
  def disconnect(sid):
      print('disconnect ', sid)

  def socketio_mw(app):
    return socketio.Middleware(sio, app)

  hass.wsgi.register_wsgi_middleware(socketio_mw)

  print('SOCKETIO SETUP!!!!!')

  return True
