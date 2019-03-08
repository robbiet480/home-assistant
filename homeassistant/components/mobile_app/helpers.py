"""Helpers for mobile_app."""
import logging
import json
from typing import Callable, Dict, Tuple

from aiohttp.web import Response

from homeassistant.core import Context
from homeassistant.helpers.typing import HomeAssistantType

from .const import (ATTR_APP_DATA, ATTR_APP_ID, ATTR_APP_NAME,
                    ATTR_APP_VERSION, DATA_DELETED_IDS, ATTR_DEVICE_NAME,
                    ATTR_MANUFACTURER, ATTR_MODEL, ATTR_OS_VERSION,
                    DATA_REGISTRATIONS, ATTR_SUPPORTS_ENCRYPTION,
                    CONF_SECRET, CONF_USER_ID, DOMAIN)

_LOGGER = logging.getLogger(__name__)


def setup_decrypt() -> Tuple[int, Callable]:
    """Return decryption function and length of key.

    Async friendly.
    """
    from nacl.secret import SecretBox
    from nacl.encoding import Base64Encoder

    def decrypt(ciphertext, key):
        """Decrypt ciphertext using key."""
        return SecretBox(key).decrypt(ciphertext, encoder=Base64Encoder)
    return (SecretBox.KEY_SIZE, decrypt)


def setup_encrypt() -> Tuple[int, Callable]:
    """Return encryption function and length of key.

    Async friendly.
    """
    from nacl.secret import SecretBox
    from nacl.encoding import Base64Encoder

    def encrypt(ciphertext, key):
        """Encrypt ciphertext using key."""
        return SecretBox(key).encrypt(ciphertext, encoder=Base64Encoder)
    return (SecretBox.KEY_SIZE, encrypt)


def _decrypt_payload(key: str, ciphertext: str) -> Dict[str, str]:
    """Decrypt encrypted payload."""
    try:
        keylen, decrypt = setup_decrypt()
    except OSError:
        _LOGGER.warning(
            "Ignoring encrypted payload because libsodium not installed")
        return None

    if key is None:
        _LOGGER.warning(
            "Ignoring encrypted payload because no decryption key known")
        return None

    key = key.encode("utf-8")
    key = key[:keylen]
    key = key.ljust(keylen, b'\0')

    try:
        message = decrypt(ciphertext, key)
        message = json.loads(message.decode("utf-8"))
        _LOGGER.debug("Successfully decrypted mobile_app payload")
        return message
    except ValueError:
        _LOGGER.warning("Ignoring encrypted payload because unable to decrypt")
        return None


def device_context(device: Dict) -> Context:
    """Generate a context from a request."""
    return Context(user_id=device[CONF_USER_ID])


def empty_okay_response(headers: Dict = None) -> Response:
    """Return a Response with empty JSON object and a 200."""
    return Response(body='{}', status=200, content_type='application/json',
                    headers=headers)


def supports_encryption() -> bool:
    """Test if we support encryption."""
    try:
        import nacl   # noqa pylint: disable=unused-import
        return True
    except OSError:
        return False


def safe_device(device: Dict) -> Dict:
    """Return a device without sensitive values."""
    # Sensitive values: webhook_id, secret, cloudhook_id, cloudhook_url
    return {
        ATTR_APP_DATA: device[ATTR_APP_DATA],
        ATTR_APP_ID: device[ATTR_APP_ID],
        ATTR_APP_NAME: device[ATTR_APP_NAME],
        ATTR_APP_VERSION: device[ATTR_APP_VERSION],
        ATTR_DEVICE_NAME: device[ATTR_DEVICE_NAME],
        ATTR_MANUFACTURER: device[ATTR_MANUFACTURER],
        ATTR_MODEL: device[ATTR_MODEL],
        ATTR_OS_VERSION: device[ATTR_OS_VERSION],
        ATTR_SUPPORTS_ENCRYPTION: device[ATTR_SUPPORTS_ENCRYPTION],
    }


def savable_state(hass: HomeAssistantType) -> Dict:
    """Return a clean object containing things that should be saved."""
    return {
        DATA_DELETED_IDS: hass.data[DOMAIN][DATA_DELETED_IDS],
        DATA_REGISTRATIONS: hass.data[DOMAIN][DATA_REGISTRATIONS]
    }


def webhook_response(data, *, device: Dict, status: int = 200,
                     headers: Dict = None) -> Response:
    """Return a encrypted response if device supports it."""
    data = json.dumps(data)

    if CONF_SECRET in device:
        keylen, encrypt = setup_encrypt()

        key = device[CONF_SECRET].encode("utf-8")
        key = key[:keylen]
        key = key.ljust(keylen, b'\0')

        enc_data = encrypt(data.encode("utf-8"), key).decode("utf-8")
        data = json.dumps({'encrypted': True, 'encrypted_data': enc_data})

    return Response(text=data, status=status, content_type='application/json',
                    headers=headers)
