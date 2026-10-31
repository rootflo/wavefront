"""The one helper modules use to store, read and mask secrets.

`ENVELOPE_ENCRYPTION_ENABLED` decides how secrets are stored:
- off: values are stored and read as they are (plaintext, as before);
- on: values are envelope-encrypted (`enc:v1:...`) and plaintext is rejected.

A value in the other mode's form raises instead of being silently used.
Masking towards API clients does not depend on the flag.

Scalar columns (an api_key) go through `protect`/`reveal`. Dict configs go
through `protect_fields`/`reveal_fields`, which JSON-encode each value so
dict-valued secrets (a service-account JSON) keep their type.

The KMS calls behind these are blocking. Async code uses the `a*` variants,
which move the work to a thread only when KMS is actually needed (an uncached
data key, or any write), so the warm read path stays on the event loop.
"""

import asyncio
import json
import threading
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from flo_cloud.envelope import (
    EnvelopeCipher,
    UnencryptedSecretError,
    is_envelope_encrypted,
)

SECRET_MASK = '********'

__all__ = [
    'SECRET_MASK',
    'SecretCipher',
    'SecretModeMismatchError',
    'UnencryptedSecretError',
]


class SecretModeMismatchError(RuntimeError):
    """An encrypted value was found while envelope encryption is disabled."""


class SecretCipher:
    def __init__(
        self,
        enabled: bool,
        envelope_factory: Optional[Callable[[], EnvelopeCipher]] = None,
    ):
        if enabled and envelope_factory is None:
            raise ValueError('envelope_factory is required when encryption is enabled')
        self._enabled = enabled
        self._envelope_factory = envelope_factory
        self._envelope: Optional[EnvelopeCipher] = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def is_encrypted(value: Any) -> bool:
        return is_envelope_encrypted(value)

    # ---- scalar values ---------------------------------------------------

    def protect(self, value: Optional[str]) -> Optional[str]:
        """Return the form to store: ciphertext when enabled, else unchanged.

        Always encrypts, even a value that already looks like `enc:v1:...`:
        accepting it as-is would let a ciphertext copied from one record be
        planted in another and decrypted there.
        """
        if not value or not self._enabled:
            return value
        return self._cipher().encrypt(value)

    def reveal(self, value: Optional[str]) -> Optional[str]:
        """Return the plaintext of a stored value."""
        if not value:
            return value
        if not self._enabled:
            self._reject_encrypted(value)
            return value
        return self._cipher().decrypt(value)

    # ---- JSON values (dict config fields) -------------------------------

    def protect_json(self, value: Any) -> Any:
        if value is None or not self._enabled:
            return value
        return self._cipher().encrypt(json.dumps(value))

    def reveal_json(self, value: Any) -> Any:
        if value is None:
            return value
        if not self._enabled:
            self._reject_encrypted(value)
            return value
        if not is_envelope_encrypted(value):
            raise UnencryptedSecretError(
                'Expected an encrypted secret, found plaintext'
            )
        return json.loads(self._cipher().decrypt(value))

    def protect_fields(
        self, config: Optional[Mapping[str, Any]], fields: Iterable[str]
    ) -> Optional[Dict[str, Any]]:
        if config is None:
            return None
        result = dict(config)
        for field in fields:
            if result.get(field) is not None:
                result[field] = self.protect_json(result[field])
        return result

    def reveal_fields(
        self, config: Optional[Mapping[str, Any]], fields: Iterable[str]
    ) -> Optional[Dict[str, Any]]:
        if config is None:
            return None
        result = dict(config)
        for field in fields:
            if result.get(field) is not None:
                result[field] = self.reveal_json(result[field])
        return result

    # ---- async variants (for code on an event loop) -----------------------

    async def aprotect(self, value: Optional[str]) -> Optional[str]:
        if not value or not self._enabled:
            return value
        return await asyncio.to_thread(self.protect, value)

    async def areveal(self, value: Optional[str]) -> Optional[str]:
        if self._needs_kms([value]):
            return await asyncio.to_thread(self.reveal, value)
        return self.reveal(value)

    async def aprotect_fields(
        self, config: Optional[Mapping[str, Any]], fields: Iterable[str]
    ) -> Optional[Dict[str, Any]]:
        if config is None or not self._enabled:
            return self.protect_fields(config, fields)
        return await asyncio.to_thread(self.protect_fields, config, fields)

    async def areveal_fields(
        self, config: Optional[Mapping[str, Any]], fields: Iterable[str]
    ) -> Optional[Dict[str, Any]]:
        fields = tuple(fields)
        values = [config.get(field) for field in fields] if config else []
        if self._needs_kms(values):
            return await asyncio.to_thread(self.reveal_fields, config, fields)
        return self.reveal_fields(config, fields)

    def _needs_kms(self, values: Iterable[Any]) -> bool:
        if not self._enabled:
            return False
        encrypted = [value for value in values if is_envelope_encrypted(value)]
        if not encrypted:
            return False
        if self._envelope is None:
            return True
        return not all(self._envelope.is_key_cached(value) for value in encrypted)

    # ---- masking (independent of the flag) -------------------------------

    @staticmethod
    def mask_fields(
        config: Optional[Mapping[str, Any]], fields: Iterable[str]
    ) -> Optional[Dict[str, Any]]:
        """Replace each present secret with `SECRET_MASK` for API responses."""
        if config is None:
            return None
        result = dict(config)
        for field in fields:
            if result.get(field) not in (None, ''):
                result[field] = SECRET_MASK
        return result

    @staticmethod
    def merge_masked(
        incoming: Mapping[str, Any],
        stored_plain: Optional[Mapping[str, Any]],
        fields: Iterable[str],
    ) -> Dict[str, Any]:
        """Keep the stored secret where an edit sent it back masked or left it out.

        An explicit `None` clears the secret.
        """
        result = dict(incoming)
        stored_plain = stored_plain or {}
        for field in fields:
            sent_back_unchanged = (
                field not in incoming or incoming[field] == SECRET_MASK
            )
            if sent_back_unchanged:
                if field in stored_plain:
                    result[field] = stored_plain[field]
                else:
                    result.pop(field, None)
        return result

    # ---- internals -------------------------------------------------------

    def _cipher(self) -> EnvelopeCipher:
        # Built on first use, so a deployment with the flag off never needs KMS.
        if self._envelope is None:
            with self._lock:
                if self._envelope is None:
                    self._envelope = self._envelope_factory()
        return self._envelope

    @staticmethod
    def _reject_encrypted(value: Any) -> None:
        if is_envelope_encrypted(value):
            raise SecretModeMismatchError(
                'Found an encrypted secret while envelope encryption is disabled'
            )
