"""
Connect two Home Assistant instances via Socket.io.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/socket_io_eventstream/
"""
import json
import threading
import urllib

import homeassistant.core as ha
import homeassistant.loader as loader
from homeassistant.const import (
    ATTR_SERVICE_DATA, EVENT_CALL_SERVICE, EVENT_SERVICE_EXECUTED,
    EVENT_STATE_CHANGED, EVENT_TIME_CHANGED, MATCH_ALL,
    HTTP_HEADER_ACCEPT_ENCODING, EVENT_HOMEASSISTANT_STOP)
from homeassistant.core import JobPriority, EventOrigin, State
from homeassistant.remote import JSONEncoder

DOMAIN = "socket_io_eventstream"
DEPENDENCIES = ["http"]
REQUIREMENTS = ["python-socketio==1.2", "eventlet==0.18.4"]

def setup(hass, config):
    """Setup the Socket.io eventstream component."""
    sub_topic = config[DOMAIN].get("subscribe_topic", None)

    import socketio
    sio = socketio.Server(async_mode="eventlet")

    @sio.on("connect", namespace='/test')
    def connect(sid, environ):
        print("connect ", sid)

    @sio.on("disconnect", namespace='/test')
    def disconnect(sid):
        print("disconnect ", sid)

    def _event_publisher(event):
        """Handle events by publishing them to Socket.io."""
        if event.origin != EventOrigin.local:
            return
        if event.event_type == EVENT_TIME_CHANGED:
            return

        # Filter out all the "event service executed" events because they
        # are only used internally by core as callbacks for blocking
        # during the interval while a service is being executed.
        # They will serve no purpose to the external system,
        # and thus are unnecessary traffic.
        # And at any rate it would cause an infinite loop to publish them
        # because publishing to an Socket.io topic itself triggers one.
        if event.event_type == EVENT_SERVICE_EXECUTED:
            return

        # PUB HERE
        data = json.dumps(event.data, cls=JSONEncoder)
        sio.emit(event.event_type, data, namespace='/test')

    # Only listen for local events if you are going to publish them.
    hass.bus.listen(MATCH_ALL, _event_publisher)

    # Process events from a remote server that are received on a queue.
    @sio.on("my event", namespace='/test')
    def _event_receiver(sid, data):
        """Receive events published by and fire them on this hass instance."""
        print("DATA", data)
        # event = json.loads(payload)
        # event_type = event.get("event_type")
        # event_data = event.get("event_data")

        # # Special case handling for event STATE_CHANGED
        # # We will try to convert state dicts back to State objects
        # # Copied over from the _handle_api_post_events_event method
        # # of the api component.
        # if event_type == EVENT_STATE_CHANGED and event_data:
        #     for key in ("old_state", "new_state"):
        #         state = State.from_dict(event_data.get(key))

        #         if state:
        #             event_data[key] = state

        # hass.bus.fire(
        #     event_type,
        #     event_data=event_data,
        #     origin=EventOrigin.remote
        # )

    hass.states.set("{domain}.initialized".format(domain=DOMAIN), True)

    def _handle_websocket_get(handler, path_match, data):
        """Handle a websocket GET request."""
        print("HEADERS", handler.headers.get('Origin'))
        environ = {
          'REQUEST_METHOD': 'GET',
          'QUERY_STRING': urllib.parse.urlencode(data),
        }

        if handler.headers.get(HTTP_HEADER_ACCEPT_ENCODING) is not None:
          environ['ACCEPT_ENCODING'] = handler.headers.get(HTTP_HEADER_ACCEPT_ENCODING)

        if handler.headers.get('Origin') is not None:
          environ['HTTP_ORIGIN'] = handler.headers.get('Origin')

        if handler.headers.get('Connection') is not None:
          environ['HTTP_CONNECTION'] = handler.headers.get('Connection')

        if handler.headers.get('Upgrade') is not None:
          environ['HTTP_UPGRADE'] = handler.headers.get('Upgrade')

        if handler.headers.get('Content-Length') is not None:
          environ['CONTENT_LENGTH'] = handler.headers.get('Content-Length')

        print("ENVIRON", environ)

        status_code = 200

        def start_response(status, response_headers):
            print("STATUS", status)
            print("response_headers", response_headers)
            handler.send_response(int(status.split(" ")[0]))
            for header in response_headers:
              handler.send_header(header[0], header[1])
            handler.end_headers()


        response_body = sio.handle_request(environ, start_response)
        for response in response_body:
          handler.wfile.write(response)
        # handler.wfile.close()

    def _handle_websocket_post(handler, path_match, data):
        """Handle a websocket GET request."""
        # post_data = data['post']
        data.pop("post", None)
        environ = {
          'REQUEST_METHOD': 'POST',
          'QUERY_STRING': urllib.parse.urlencode(data),
          'wsgi.input': handler.rfile,
        }

        if handler.headers.get(HTTP_HEADER_ACCEPT_ENCODING) is not None:
          environ['ACCEPT_ENCODING'] = handler.headers.get(HTTP_HEADER_ACCEPT_ENCODING)

        if handler.headers.get('Origin') is not None:
          environ['HTTP_ORIGIN'] = handler.headers.get('Origin')

        if handler.headers.get('Connection') is not None:
          environ['HTTP_CONNECTION'] = handler.headers.get('Connection')

        if handler.headers.get('Upgrade') is not None:
          environ['HTTP_UPGRADE'] = handler.headers.get('Upgrade')

        if handler.headers.get('Content-Length') is not None:
          environ['CONTENT_LENGTH'] = handler.headers.get('Content-Length')

        print("ENVIRON", environ)

        status_code = 200

        def start_response(status, response_headers):
            print("STATUS", status)
            print("response_headers", response_headers)
            handler.send_response(int(status.split(" ")[0]))
            for header in response_headers:
              handler.send_header(header[0], header[1])
            handler.end_headers()


        response_body = sio.handle_request(environ, start_response)
        for response in response_body:
          handler.wfile.write(response)
        # handler.wfile.close()

    # Uncomment these next 2 lines and change async_mode to `threading` to
    # enable the built in HTTP server to handle websockets.
    # NOTE: threading only supports long polling. See eventlet implementation
    # below for true websocket support.

    # hass.http.register_path('GET', '/socket.io/', _handle_websocket_get)
    # hass.http.register_path('POST', '/socket.io/', _handle_websocket_post)

    # Eventlet
    # Problem with this is that messages don't transmit properly right now
    # I assume this is due to threading.
    # The other problem being that it has to run on it's own port to work.
    app = socketio.Middleware(sio)
    import eventlet

    def start():
      eventlet.wsgi.server(eventlet.listen(('', 8124)), app)

    hass.bus.listen_once(
        ha.EVENT_HOMEASSISTANT_START,
        lambda event:
        threading.Thread(target=start, daemon=True,
                         name='Socket.io-server').start())

    return True
