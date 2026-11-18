import base64
import functools
import json
import jwt
import hashlib

from datetime import datetime
from datetime import timedelta
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
        token_prefix: str,
        issuer: str,
        audience: str,
        algorithm: TokenAlgorithms = TokenAlgorithms.PS256,
        public_key_cache_seconds: float | str | None = None,
        public_key_refresh_min_seconds: float | str | None = None,
    ):
        """
        Args:
            public_key_cache_seconds: How long the KMS public key is reused for
                verifying tokens. 0 disables the cache (fetch on every request).
                Default 600. See common_module.security.public_key_cache.
            public_key_refresh_min_seconds: Minimum time between refetches
                triggered by a token whose signature doesn't match (key
                rotation). Default 60.
        """
        self._keys = PublicKeyCache(
            lambda: self.kms_signer.get_public_key_pem(),
            cache_seconds=public_key_cache_seconds,
            refresh_min_seconds=public_key_refresh_min_seconds,
        )
        self.algorithm = algorithm.value
        self.token_expiry = int(token_expiry)
        self.temporary_token_expiry = int(temporary_token_expiry)
        self.kms_signer = kms_signer
        self.token_prefix = token_prefix
        self.issuer = issuer
        self.audience = audience

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

        now = datetime.now()
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

        token = f'{message}.{signature}'
        return f'{self.token_prefix}{token}'

    async def create_token_async(self, **kwargs: Any) -> str:
        """``create_token`` with the KMS signing call off the event loop."""
        return await run_in_pool('kms', functools.partial(self.create_token, **kwargs))

    # Tokens are verified locally with the cached KMS public key; the remote KMS
    # verify (a network call per request, on the event loop) is gone. jwt.decode
    # already checked the signature with the same key and algorithm.

    def decode_token(self, token: str) -> dict:
        """Verify and decode ``token``. Blocking on a cache miss: for sync callers only."""
        clean_token = self._strip_prefix(token)
        return (
            self._keys.verify(lambda key: self._decode_with_key(clean_token, key)) or {}
        )

    async def decode_token_async(self, token: str) -> dict:
        """``decode_token`` without blocking the event loop. Same results:
        ValueError for a bad format, {} for a bad signature, jwt errors otherwise."""
        clean_token = self._strip_prefix(token)
        return (
            await self._keys.averify(
                lambda key: self._decode_with_key(clean_token, key)
            )
            or {}
        )

    def _strip_prefix(self, token: str) -> str:
        if not token.startswith(self.token_prefix):
            raise ValueError(
                f'Invalid token format: missing prefix "{self.token_prefix}"'
            )
        clean_token = token[len(self.token_prefix) :]
        header_b64, payload_b64, signature_b64 = clean_token.split('.')
        self._base64url_decode(signature_b64)
        return clean_token

    def _decode_with_key(
        self, clean_token: str, public_key_pem: bytes | str
    ) -> dict | None:
        """Decoded claims, or None when the signature doesn't match this key."""
        try:
            return jwt.decode(
                clean_token,
                public_key_pem,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
            )
        except jwt.InvalidSignatureError:
            return None

    def _base64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    def _base64url_decode(self, data: str) -> bytes:
        padding = '=' * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)
