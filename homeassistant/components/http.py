"""This module provides WSGI application to serve the Home Assistant API."""
import hmac
import json
import logging
import mimetypes
import threading
import re

import homeassistant.core as ha
import homeassistant.remote as rem
from homeassistant import util
from homeassistant.const import (
    SERVER_PORT, HTTP_HEADER_HA_AUTH, HTTP_HEADER_CACHE_CONTROL)
from homeassistant.helpers.entity import split_entity_id
import homeassistant.util.dt as dt_util

DOMAIN = "http"
REQUIREMENTS = ("eventlet==0.18.4", "static3==0.7.0", "Werkzeug==0.11.5",)

CONF_API_PASSWORD = "api_password"
CONF_SERVER_HOST = "server_host"
CONF_SERVER_PORT = "server_port"
CONF_DEVELOPMENT = "development"
CONF_SSL_CERTIFICATE = 'ssl_certificate'
CONF_SSL_KEY = 'ssl_key'

DATA_API_PASSWORD = 'api_password'

_FINGERPRINT = re.compile(r'^(.+)-[a-z0-9]{32}\.(\w+)$', re.IGNORECASE)

_LOGGER = logging.getLogger(__name__)

def setup(hass, config):
    """Set up the HTTP API and debug interface."""
    conf = config.get(DOMAIN, {})

    api_password = util.convert(conf.get(CONF_API_PASSWORD), str)
    server_host = conf.get(CONF_SERVER_HOST, '0.0.0.0')
    server_port = conf.get(CONF_SERVER_PORT, SERVER_PORT)
    development = str(conf.get(CONF_DEVELOPMENT, "")) == "1"
    ssl_certificate = conf.get(CONF_SSL_CERTIFICATE)
    ssl_key = conf.get(CONF_SSL_KEY)

    server = HomeAssistantWSGI(
        hass,
        development=development,
        server_host=server_host,
        server_port=server_port,
        api_password=api_password,
        ssl_certificate=ssl_certificate,
        ssl_key=ssl_key,
    )

    hass.bus.listen_once(
        ha.EVENT_HOMEASSISTANT_START,
        lambda event:
        threading.Thread(target=server.start, daemon=True,
                         name='WSGI-server').start())

    hass.wsgi = server
    hass.config.api = rem.API(server_host if server_host != '0.0.0.0'
                              else util.get_local_ip(),
                              api_password, server_port,
                              ssl_certificate is not None)

    return True


def request_class():
    """Generate request class.

    Done in method because of imports.
    """
    from werkzeug.exceptions import BadRequest
    from werkzeug.wrappers import BaseRequest, AcceptMixin
    from werkzeug.utils import cached_property

    class Request(BaseRequest, AcceptMixin):
        """Base class for incoming requests."""

        @cached_property
        def json(self):
            """Get the result of json.loads if possible."""
            if not self.data:
                return None
            # elif 'json' not in self.environ.get('CONTENT_TYPE', ''):
            #     raise BadRequest('Not a JSON request')
            try:
                return json.loads(self.data.decode(
                    self.charset, self.encoding_errors))
            except (TypeError, ValueError):
                raise BadRequest('Unable to read JSON request')

    return Request


def routing_map(hass):
    """Generate empty routing map with HA validators."""
    from werkzeug.routing import Map, BaseConverter, ValidationError

    class EntityValidator(BaseConverter):
        """Validate entity_id in urls."""

        regex = r"(\w+)\.(\w+)"

        def __init__(self, url_map, exist=True, domain=None):
            """Initilalize entity validator."""
            super().__init__(url_map)
            self._exist = exist
            self._domain = domain

        def to_python(self, value):
            """Validate entity id."""
            if self._exist and hass.states.get(value) is None:
                raise ValidationError()
            if self._domain is not None and \
               split_entity_id(value)[0] != self._domain:
                raise ValidationError()

            return value

        def to_url(self, value):
            """Convert entity_id for a url."""
            return value

    class DateValidator(BaseConverter):
        """Validate dates in urls."""

        regex = r'\d{4}-(0[1-9])|(1[012])-((0[1-9])|([12]\d)|(3[01]))'

        def to_python(self, value):
            """Validate and convert date."""
            parsed = dt_util.parse_date(value)

            if value is None:
                raise ValidationError()

            return parsed

        def to_url(self, value):
            """Convert date to url value."""
            return value.isoformat()

    return Map(converters={
        'entity': EntityValidator,
        'date': DateValidator,
    })


class HomeAssistantWSGI(object):
    """WSGI server for Home Assistant."""

    # pylint: disable=too-many-instance-attributes, too-many-locals
    # pylint: disable=too-many-arguments

    def __init__(self, hass, development, api_password, ssl_certificate,
                 ssl_key, server_host, server_port):
        """Initilalize the WSGI Home Assistant server."""
        from werkzeug.wrappers import Response

        Response.mimetype = 'text/html'

        # pylint: disable=invalid-name
        self.Request = request_class()
        self.url_map = routing_map(hass)
        self.views = {}
        self.hass = hass
        self.extra_apps = {}
        self.middleware = []
        self.development = development
        self.api_password = api_password
        self.ssl_certificate = ssl_certificate
        self.ssl_key = ssl_key
        self.server_host = server_host
        self.server_port = server_port
        self.event_forwarder = None

    def register_view(self, view):
        """Register a view with the WSGI server.

        The view argument must be a class that inherits from HomeAssistantView.
        It is optional to instantiate it before registering; this method will
        handle it either way.
        """
        from werkzeug.routing import Rule

        if view.name in self.views:
            _LOGGER.warning("View '%s' is being overwritten", view.name)
        if isinstance(view, type):
            # Instantiate the view, if needed
            view = view(self.hass)

        self.views[view.name] = view

        rule = Rule(view.url, endpoint=view.name)
        self.url_map.add(rule)
        for url in view.extra_urls:
            rule = Rule(url, endpoint=view.name)
            self.url_map.add(rule)

    def register_redirect(self, url, redirect_to):
        """Register a redirect with the server.

        If given this must be either a string or callable. In case of a
        callable it’s called with the url adapter that triggered the match and
        the values of the URL as keyword arguments and has to return the target
        for the redirect, otherwise it has to be a string with placeholders in
        rule syntax.
        """
        from werkzeug.routing import Rule

        self.url_map.add(Rule(url, redirect_to=redirect_to))

    def register_static_path(self, url_root, path):
        """Register a folder to serve as a static path."""
        from static import Cling

        headers = []

        if not self.development:
            # 1 year in seconds
            cache_time = 365 * 86400

            headers.append({
                'prefix': '',
                HTTP_HEADER_CACHE_CONTROL:
                "public, max-age={}".format(cache_time)
            })

        self.register_wsgi_app(url_root, Cling(path, headers=headers))

    def register_wsgi_app(self, url_root, app):
        """Register a path to serve a WSGI app."""
        if url_root in self.extra_apps:
            _LOGGER.warning("Url root '%s' is being overwritten", url_root)

        self.extra_apps[url_root] = app

    def register_wsgi_middleware(self, middleware):
        """Add to the WSGI middleware stack."""
        self.middleware.append(middleware)

    def start(self):
        """Start the wsgi server."""
        from eventlet import wsgi
        import eventlet

        sock = eventlet.listen((self.server_host, self.server_port))
        if self.ssl_certificate:
            eventlet.wrap_ssl(sock, certfile=self.ssl_certificate,
                              keyfile=self.ssl_key, server_side=True)

        app = self
        for middleware in self.middleware:
            app = middleware(app)

        wsgi.server(sock, app)

    def dispatch_request(self, request):
        """Handle incoming request."""
        from werkzeug.exceptions import (
            MethodNotAllowed, NotFound, BadRequest, Unauthorized,
        )
        from werkzeug.routing import RequestRedirect

        with request:
            adapter = self.url_map.bind_to_environ(request.environ)
            try:
                endpoint, values = adapter.match()
                resp = self.views[endpoint].handle_request(request, **values)
                return resp
            except RequestRedirect as ex:
                return ex
            except (BadRequest, NotFound, MethodNotAllowed,
                    Unauthorized) as ex:
                resp = ex.get_response(request.environ)
                if request.accept_mimetypes.accept_json:
                    resp.data = json.dumps({
                        "result": "error",
                        "message": str(ex),
                    })
                    resp.mimetype = "application/json"
                return resp

    def base_app(self, environ, start_response):
        """WSGI Handler of requests to base app."""
        request = self.Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        """Handle a request for base app + extra apps."""
        from werkzeug.wsgi import DispatcherMiddleware

        app = DispatcherMiddleware(self.base_app, self.extra_apps)
        # Strip out any cachebusting MD5 fingerprints
        fingerprinted = _FINGERPRINT.match(environ.get('PATH_INFO', ''))
        if fingerprinted:
            environ['PATH_INFO'] = "{}.{}".format(*fingerprinted.groups())
        return app(environ, start_response)


class HomeAssistantView(object):
    """Base view for all views."""

    extra_urls = []
    requires_auth = True  # Views inheriting from this class can override this

    def __init__(self, hass):
        """Initilalize the base view."""
        from werkzeug.wrappers import Response

        if not hasattr(self, 'url'):
            class_name = self.__class__.__name__
            raise AttributeError(
                '{0} missing required attribute "url"'.format(class_name)
            )

        if not hasattr(self, 'name'):
            class_name = self.__class__.__name__
            raise AttributeError(
                '{0} missing required attribute "name"'.format(class_name)
            )

        self.hass = hass
        # pylint: disable=invalid-name
        self.Response = Response

    def handle_request(self, request, **values):
        """Handle request to url."""
        from werkzeug.exceptions import (
            MethodNotAllowed, Unauthorized, BadRequest,
        )

        try:
            handler = getattr(self, request.method.lower())
        except AttributeError:
            raise MethodNotAllowed

        # Auth code verbose on purpose
        authenticated = False

        if self.hass.wsgi.api_password is None:
            authenticated = True

        elif hmac.compare_digest(request.headers.get(HTTP_HEADER_HA_AUTH, ''),
                                 self.hass.wsgi.api_password):
            # A valid auth header has been set
            authenticated = True

        elif hmac.compare_digest(request.args.get(DATA_API_PASSWORD, ''),
                                 self.hass.wsgi.api_password):
            authenticated = True

        else:
            # Do we still want to support passing it in as post data?
            try:
                json_data = request.json
                if (json_data is not None and
                        hmac.compare_digest(
                            json_data.get(DATA_API_PASSWORD, ''),
                            self.hass.wsgi.api_password)):
                    authenticated = True
            except BadRequest:
                pass

        if self.requires_auth and not authenticated:
            raise Unauthorized()

        request.authenticated = authenticated

        result = handler(request, **values)

        if isinstance(result, self.Response):
            # The method handler returned a ready-made Response, how nice of it
            return result

        status_code = 200

        if isinstance(result, tuple):
            result, status_code = result

        return self.Response(result, status=status_code)

    def json(self, result, status_code=200):
        """Return a JSON response."""
        msg = json.dumps(
            result,
            sort_keys=True,
            cls=rem.JSONEncoder
        ).encode('UTF-8')
        return self.Response(msg, mimetype="application/json",
                             status=status_code)

    def json_message(self, error, status_code=200):
        """Return a JSON message response."""
        return self.json({'message': error}, status_code)

    def file(self, request, fil, mimetype=None):
        """Return a file."""
        from werkzeug.wsgi import wrap_file
        from werkzeug.exceptions import NotFound

        if isinstance(fil, str):
            if mimetype is None:
                mimetype = mimetypes.guess_type(fil)[0]

            try:
                fil = open(fil)
            except IOError:
                raise NotFound()

        return self.Response(wrap_file(request.environ, fil),
                             mimetype=mimetype, direct_passthrough=True)
