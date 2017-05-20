"""
Support for hass.io DynDNS registration and updating.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/dyndns/
"""

import os
import logging
import asyncio
import json
import datetime
import voluptuous as vol
from arroyo import crypto
from asyncme.client import AsyncmeClient as Client
from asyncme.challenges import (ChallengeType, ChallengeFailure,
                                DNS01ChallengeHandler)
from OpenSSL import crypto as openssl

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.helpers import event
from homeassistant.loader import get_component
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DIRECTORY_URL = 'https://acme-staging.api.letsencrypt.org/directory'

BASE_URL = 'https://bkujetwt7d.execute-api.us-west-2.amazonaws.com/Production/'

STATUS_URL = '{}record/change_status'.format(BASE_URL)

TXT_URL = '{}record/txt_record'.format(BASE_URL)

REGISTER_URL = '{}record/update'.format(BASE_URL)

IPV6_URL = 'http://v6.ipv6-test.com/api/myip.php?json'

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['asyncme==0.4.1']

DOMAIN = 'dyndns'

CONF_DOMAIN_NAME = 'domain_name'
CONF_REQUEST_CERTIFICATE = 'request_certificate'

_CONFIGURING = {}

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_DOMAIN_NAME): cv.string,
        vol.Optional(CONF_REQUEST_CERTIFICATE, default=True): cv.boolean
    }),
}, extra=vol.ALLOW_EXTRA)


def request_configuration(hass, client):
    """Request configuration steps from the user."""
    configurator = get_component('configurator')

    if DOMAIN in _CONFIGURING:
        return

    @asyncio.coroutine
    def configuration_callback(callback_data):
        """Handle the submitted configuration."""
        yield from client.accept_terms()

        hass.async_add_job(configurator.request_done, _CONFIGURING[DOMAIN])

    _CONFIGURING[DOMAIN] = configurator.request_config(
        hass, "Let's Encrypt", configuration_callback,
        description=("You must accept the terms of service for Let's Encrypt. "
                     "Click here to view the "),
        submit_caption="I read and accept the terms",
        link_name="terms of service",
        link_url=client.terms_of_service
    )


@asyncio.coroutine
def async_setup(hass, config):
    """Set up the DynDNS component."""
    websession = async_get_clientsession(hass)

    domain_name = config[DOMAIN][CONF_DOMAIN_NAME]

    client = None

    acme_key = None
    acme_key_path = hass.config.path('.ha_dyndns_acme_key.pem')

    if os.path.isfile(acme_key_path):
        _LOGGER.info('acme_key.pem exists, lets use it!')
        acme_key = crypto.PrivateKey.from_file(acme_key_path)
    else:
        _LOGGER.info('acme_key.pem does not exist, lets generate one!')
        acme_key = crypto.PrivateKey.generate('RSA')
        acme_key.to_file(acme_key_path,
                         encoding=crypto.EncodingType.PEM)

    client = yield from Client.connect(DIRECTORY_URL, acme_key, loop=hass.loop)

    if client.has_accepted_terms() is False:
        _LOGGER.error('You havent accepted the Lets Encrypt terms yet!')
        hass.async_add_job(request_configuration, hass, client)

    @asyncio.coroutine
    def update_dyndns(now):
        """Update DynDNS record(s)."""
        yield from update_record(websession, domain_name)

    @asyncio.coroutine
    def lets_encrypt(now):
        """Check if the certificate needs to be generated/renewed."""
        cert_path = hass.config.path('.ha_dyndns_cert.pem')
        if os.path.isfile(cert_path):
            with open(cert_path, 'rb') as file:
                cert = openssl.load_certificate(openssl.FILETYPE_PEM,
                                                file.read())
                expiry_bytes = cert.get_notAfter().decode('utf-8')
                expiry_time = datetime.datetime.strptime(expiry_bytes,
                                                         "%Y%m%d%H%M%SZ")

                days_remain = (expiry_time.date() - datetime.date.today()).days

                if days_remain >= 7:
                    _LOGGER.info('Certificate still has %s days remaining '
                                 'before expiration, not renewing now.',
                                 days_remain)
                    return False

        new_certificate = yield from acme_client(hass, websession,
                                                 client, domain_name)

        new_certificate.to_file(cert_path, encoding=crypto.EncodingType.PEM)
        return True

    _dt = dt_util.utcnow() + datetime.timedelta(seconds=30)

    yield from update_dyndns(0)

    event.async_track_utc_time_change(
        hass, update_dyndns,
        hour=_dt.hour, minute=_dt.minute, second=_dt.second)

    if config[DOMAIN][CONF_REQUEST_CERTIFICATE] is True:
        acme_key = None
        acme_key_path = hass.config.path('.ha_dyndns_acme_key.pem')

        if os.path.isfile(acme_key_path):
            _LOGGER.info('acme_key.pem exists, lets use it!')
            acme_key = crypto.PrivateKey.from_file(acme_key_path)
        else:
            _LOGGER.info('acme_key.pem does not exist, lets generate one!')
            acme_key = crypto.PrivateKey.generate('RSA')
            acme_key.to_file(acme_key_path,
                             encoding=crypto.EncodingType.PEM)

        client = yield from Client.connect(DIRECTORY_URL, acme_key,
                                           loop=hass.loop)

        yield from lets_encrypt(0)
        event.async_track_utc_time_change(
            hass, lets_encrypt,
            hour=_dt.hour, minute=_dt.minute, second=_dt.second)

    return True


class HASSDynDNSHandler(DNS01ChallengeHandler):
    # pylint: disable=too-few-public-methods
    """An AcmeChallengeHandler used to handle DNS-01 challenges for hass.io."""

    def __init__(self, *args, session, subdomain: str, **kwargs):
        """Init the challenge."""
        super().__init__(*args, **kwargs)
        self.change_id = None
        self.session = session
        self.payload = json.dumps({'subdomain': subdomain,
                                   'challenge': self.txt_record_contents()})

    async def _do_cleanup(self):
        _LOGGER.info('Deleting TXT record from Route53')

        async with self.session.delete(TXT_URL, data=self.payload) as resp:
            await resp.json()

    async def _do_perform(self):
        _LOGGER.info('Creating TXT record on Route53')

        async with self.session.post(TXT_URL, data=self.payload) as resp:
            json_body = await resp.json()
            self.change_id = json_body['change_response']['Id']

    async def _route_53_is_insync(self):
        params = {'change_id': self.change_id}

        async with self.session.get(STATUS_URL, params=params) as resp:
            json_body = await resp.json()
            return json_body['Status'] == 'INSYNC'

    async def _wait_for_route_53(self, attempts: int = 30):
        _LOGGER.info('Waiting for Route53 to be INSYNC')

        for i in range(attempts):

            _LOGGER.info('Checking Route53 for INSYNC, attempt %s', i)

            await asyncio.sleep(5)

            is_insync = await self._route_53_is_insync()

            if is_insync:
                _LOGGER.info('Route53 is INSYNC')
                return
            else:
                _LOGGER.debug(
                    'Route53 is still not ready on '
                    'Attempt %d/%d', (i + 1), attempts
                )
                break

        else:
            msg = 'Route 53 failed to propagate in time'
            _LOGGER.error(msg)
            raise ChallengeFailure(msg)

    async def _do_verify(self):
        await self._wait_for_route_53()


async def acme_client(hass, websession, client, subdomain):
    """Get the certificates."""
    base_domain = 'hass.io'
    domain = '{}.{}'.format(subdomain, base_domain)

    authed = await client.is_authed_for_domain(domain)
    if not authed:

        challenges = await client.get_domain_challenges(domain)
        dns_01 = challenges[ChallengeType.DNS_01]

        handler = HASSDynDNSHandler(dns_01, domain, subdomain=subdomain,
                                    session=websession, loop=hass.loop)

        try:
            await handler.perform()
        except ChallengeFailure:
            raise RuntimeError('Failed to satisfy ACME challenge')

        # Ensure that we gained authorization for the domain
        for _ in range(10):
            if await client.is_authed_for_domain(domain):
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Failed to gain authorization for domain')

    cert_key_path = hass.config.path('.ha_dyndns_cert_key.pem')

    cert_key = crypto.PrivateKey.generate('RSA', size=4096)
    cert_key.to_file(cert_key_path, encoding=crypto.EncodingType.PEM)

    csr = crypto.x509CertSignReq.generate(cert_key, domain)

    cert = await client.request_cert(csr)

    return cert


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
            _LOGGER.warning('You don\'t have an IPv6 address, continuing!')
        else:
            msg = 'Error encountered when attempting to determine IPv6 address'
            _LOGGER.error(msg, err)

    async with websession.post(REGISTER_URL,
                               data=json.dumps(payload)) as resp:
        _LOGGER.info('Registered!')
