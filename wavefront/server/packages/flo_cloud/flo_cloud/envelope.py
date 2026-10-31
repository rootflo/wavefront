"""Envelope encryption for secrets stored in Postgres, Redis or YAML.

Each value gets its own random 32-byte data key (DEK). The value is encrypted
locally with AES-256-GCM and only the DEK is sent to KMS to be wrapped, so the
KMS plaintext limits (about 190 B on Azure RSA-OAEP) never apply to the secret.

Stored format: ``enc:v1:<b64 wrapped DEK>:<b64 nonce || ciphertext || tag>``.
The prefix tells ciphertext apart from base64-looking plaintext and versions
the format.

Unwrapped DEKs are cached per process (never the secrets themselves), so after
the first decrypt of a value only local AES runs.
"""

import base64
import hashlib
import os
import threading
import time
from collections import OrderedDict
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ._types import FloCipher
from .exceptions import KmsError

ENVELOPE_PREFIX = 'enc:v1:'

_DEK_BYTES = 32
_NONCE_BYTES = 12
# Binds the ciphertext to the format version; a v2 reader cannot be fed v1 bytes.
_AAD = ENVELOPE_PREFIX.encode('utf-8')


class UnencryptedSecretError(ValueError):
    """A value that should be envelope-encrypted is not (missing `enc:v1:`)."""


def is_envelope_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(ENVELOPE_PREFIX)


class _DekCache:
    """Bounded LRU of wrapped-DEK digest -> DEK, with a TTL per entry."""

    def __init__(self, max_entries: int, ttl_seconds: float):
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[bytes, tuple[float, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: bytes) -> Optional[bytes]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, dek = entry
            if time.monotonic() >= expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return dek

    def put(self, key: bytes, dek: bytes) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl_seconds, dek)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


class EnvelopeCipher:
    def __init__(
        self,
        kms_cipher: FloCipher,
        cache_max_entries: int = 1024,
        cache_ttl_seconds: float = 3600,
    ):
        self._kms = kms_cipher
        self._dek_cache = _DekCache(cache_max_entries, cache_ttl_seconds)

    @staticmethod
    def is_encrypted(value: object) -> bool:
        return is_envelope_encrypted(value)

    def encrypt(self, plaintext: str) -> str:
        dek = AESGCM.generate_key(bit_length=_DEK_BYTES * 8)
        nonce = os.urandom(_NONCE_BYTES)
        sealed = AESGCM(dek).encrypt(nonce, plaintext.encode('utf-8'), _AAD)
        wrapped_dek = self._kms.encrypt(dek)
        self._dek_cache.put(_cache_key(wrapped_dek), dek)
        return _format(wrapped_dek, nonce + sealed)

    def decrypt(self, value: str) -> str:
        wrapped_dek, payload = _parse(value)
        dek = self._unwrap(wrapped_dek)
        nonce, sealed = payload[:_NONCE_BYTES], payload[_NONCE_BYTES:]
        try:
            plaintext = AESGCM(dek).decrypt(nonce, sealed, _AAD)
        except InvalidTag as e:
            raise KmsError('Failed to decrypt secret') from e
        return plaintext.decode('utf-8')

    def is_key_cached(self, value: str) -> bool:
        """True when decrypting `value` needs no KMS call (its DEK is cached)."""
        try:
            wrapped_dek, _payload = _parse(value)
        except (UnencryptedSecretError, KmsError):
            return False
        return self._dek_cache.get(_cache_key(wrapped_dek)) is not None

    def rewrap(self, value: str) -> str:
        """Re-wrap the DEK with the current KMS key; the secret itself is untouched.

        Bypasses the cache so the unwrap really exercises the old key version.
        """
        wrapped_dek, payload = _parse(value)
        dek = self._kms.decrypt(wrapped_dek)
        new_wrapped_dek = self._kms.encrypt(dek)
        self._dek_cache.put(_cache_key(new_wrapped_dek), dek)
        return _format(new_wrapped_dek, payload)

    def _unwrap(self, wrapped_dek: bytes) -> bytes:
        key = _cache_key(wrapped_dek)
        dek = self._dek_cache.get(key)
        if dek is None:
            dek = self._kms.decrypt(wrapped_dek)
            if len(dek) != _DEK_BYTES:
                raise KmsError('Failed to decrypt secret')
            self._dek_cache.put(key, dek)
        return dek


def _cache_key(wrapped_dek: bytes) -> bytes:
    return hashlib.sha256(wrapped_dek).digest()


def _format(wrapped_dek: bytes, payload: bytes) -> str:
    return (
        ENVELOPE_PREFIX
        + base64.b64encode(wrapped_dek).decode('ascii')
        + ':'
        + base64.b64encode(payload).decode('ascii')
    )


def _parse(value: str) -> tuple[bytes, bytes]:
    if not is_envelope_encrypted(value):
        raise UnencryptedSecretError('Expected an encrypted secret, found plaintext')
    try:
        wrapped_b64, payload_b64 = value[len(ENVELOPE_PREFIX) :].split(':', 1)
        wrapped_dek = base64.b64decode(wrapped_b64, validate=True)
        payload = base64.b64decode(payload_b64, validate=True)
    except ValueError as e:
        raise KmsError('Failed to decrypt secret') from e
    if len(payload) <= _NONCE_BYTES:
        raise KmsError('Failed to decrypt secret')
    return wrapped_dek, payload
