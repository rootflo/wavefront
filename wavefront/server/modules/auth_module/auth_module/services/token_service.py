import base64
import binascii
import functools
import json
import jwt
import hashlib

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from common_module.blocking_io import run_in_pool
from common_module.security.public_key_cache import PublicKeyCache
from flo_cloud._types import FloSigner


class TokenAlgorithms(str, Enum):
    RS256 = 'RS256'
    PS256 = 'PS256'
    ES256 = 'ES256'
    ES384 = 'ES384'
    ES512 = 'ES512'
    RS384 = 'RS384'
    RS512 = 'RS512'
    PS384 = 'PS384'
    PS512 = 'PS512'


class TokenService:
    def __init__(
        self,
        kms_signer: FloSigner,
        *,
        token_expiry: int,
        temporary_token_expiry: int,
        app_env: str,
        issuer: str,
        audience: str,
        validation_issuers: list[str],
        token_prefix: str,
        algorithm: TokenAlgorithms = TokenAlgorithms.PS256,
        public_key_cache_seconds: float | str | None = None,
        public_key_refresh_min_seconds: float | str | None = None,
    ):
        """
        Args:
            public_key_cache_seconds: How long the KMS public key is reused for
                verifying tokens. 0 disables the cache (fetch on every request).
                Default 600.
            public_key_refresh_min_seconds: Minimum time between refetches
                triggered by a token whose signature doesn't match (key
                rotation). Default 60.
        """
        self._keys = PublicKeyCache(
            self._fetch_public_key,
            cache_seconds=public_key_cache_seconds,
            refresh_min_seconds=public_key_refresh_min_seconds,
        )
        self.public_key_cache_seconds = self._keys.cache_seconds
        self.public_key_refresh_min_seconds = self._keys.refresh_min_seconds
        self.algorithm = algorithm.value
        self.token_expiry = int(token_expiry)
        self.temporary_token_expiry = int(temporary_token_expiry)
        self.kms_signer = kms_signer
        self.app_env = app_env
        self.issuer = issuer
        self.audience = audience
        self.validation_issuers = validation_issuers
        self.token_prefix = token_prefix

    def create_token(
        self,
        sub: str | None = None,
        user_id: str | None = None,
        role_id: str | None = None,
        expiry: int | None = None,
        payload: dict[str, Any] | None = None,
        is_temporary: bool = False,
    ) -> str:
        if not is_temporary and (sub is None or user_id is None or role_id is None):
            raise ValueError('Required values are missing for creating a token')

        now = datetime.now(timezone.utc)
        data = {
            key: value
            for key, value in [
                ('sub', sub),
                ('user_id', user_id),
                ('role_id', role_id),
            ]
            if value is not None
        }

        expiry_seconds = expiry or (
            self.temporary_token_expiry if is_temporary else self.token_expiry
        )
        data['exp'] = int((now + timedelta(seconds=expiry_seconds)).timestamp())
        data['iat'] = int(now.timestamp())
        data['iss'] = self.issuer
        data['aud'] = self.audience

        if payload:
            data.update(payload)
        header = {'alg': self.algorithm, 'typ': 'JWT'}

        header_b64 = self._base64url_encode(json.dumps(header).encode())
        payload_b64 = self._base64url_encode(json.dumps(data).encode())
        message = f'{header_b64}.{payload_b64}'

        digest = hashlib.sha256(message.encode()).digest()

        signature = self.kms_signer.sign(message=digest)
        signature = self._base64url_encode(signature)

        return f'{message}.{signature}'

    async def create_token_async(self, **kwargs: Any) -> str:
        """``create_token`` with the KMS signing call off the event loop."""
        return await run_in_pool('kms', functools.partial(self.create_token, **kwargs))

    # -- verification ----------------------------------------------------------
    #
    # Tokens are verified locally against the KMS public key, with the key
    # cached for public_key_cache_seconds. This used to call KMS twice per
    # request (a remote verify plus a key fetch), on the event loop. jwt.decode
    # already did a full signature check with the same key and algorithm, so the
    # remote verify added a network call and no protection.
    #
    # Trade-off: a KMS key that is disabled or rotated is noticed when the cache
    # refreshes, not instantly. public_key_cache_seconds = 0 turns the cache off
    # (key fetched on every request, off the loop) for instant revocation.

    def decode_token(self, token: str) -> dict:
        """Verify and decode ``token``. Blocking on a cache miss: for sync callers only."""
        self._check_format(token)
        return self._keys.verify(lambda key: self._decode_with_key(token, key)) or {}

    async def decode_token_async(self, token: str) -> dict:
        """Verify and decode ``token`` without blocking the event loop.

        Same results as ``decode_token``: {} for a bad signature, and
        jwt.InvalidTokenError (or a subclass) for malformed or expired tokens.
        """
        self._check_format(token)
        return (
            await self._keys.averify(lambda key: self._decode_with_key(token, key))
            or {}
        )

    def _check_format(self, token: str) -> None:
        try:
            header_b64, payload_b64, signature_b64 = token.split('.')
        except ValueError as e:
            raise jwt.InvalidTokenError('Invalid token format') from e
        try:
            self._base64url_decode(signature_b64)
        except (binascii.Error, ValueError) as e:
            raise jwt.InvalidTokenError('Invalid token format') from e

    def _decode_with_key(self, token: str, public_key_pem: bytes | str) -> dict | None:
        """Decoded claims, or None when the signature doesn't match this key."""
        try:
            return jwt.decode(
                token,
                public_key_pem,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
            )
        except jwt.InvalidSignatureError:
            return None
        except jwt.InvalidTokenError:
            raise
        except (binascii.Error, ValueError, json.JSONDecodeError, KeyError) as e:
            raise jwt.InvalidTokenError('Invalid token') from e
        except Exception as e:
            raise jwt.InvalidTokenError('Invalid token') from e

    def _fetch_public_key(self) -> bytes | str:
        try:
            return self.kms_signer.get_public_key_pem()
        except Exception as e:
            raise jwt.InvalidTokenError('Invalid token') from e

    def _base64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    def _base64url_decode(self, data: str) -> bytes:
        padding = '=' * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)
