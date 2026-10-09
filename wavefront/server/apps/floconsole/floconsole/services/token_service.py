import base64
import json
import jwt
import hashlib

from datetime import datetime
from datetime import timedelta
from enum import Enum
from typing import Any
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
    ):
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

    def decode_token(self, token: str) -> dict:
        # Validate and remove prefix
        if not token.startswith(self.token_prefix):
            raise ValueError(
                f'Invalid token format: missing prefix "{self.token_prefix}"'
            )

        # Remove the prefix
        clean_token = token[len(self.token_prefix) :]
        header_b64, payload_b64, signature_b64 = clean_token.split('.')

        message = f'{header_b64}.{payload_b64}'
        digest = hashlib.sha256(message.encode()).digest()
        signature = self._base64url_decode(signature_b64)

        is_valid = self.kms_signer.verify(message=digest, signature=signature)
        if not is_valid:
            return {}

        public_key_pem = self.kms_signer.get_public_key_pem()

        decoded = jwt.decode(
            clean_token,
            public_key_pem,
            algorithms=[self.algorithm],
            issuer=self.issuer,
            audience=self.audience,
        )
        return decoded

    def _base64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    def _base64url_decode(self, data: str) -> bytes:
        padding = '=' * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)
