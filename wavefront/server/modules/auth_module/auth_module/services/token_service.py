import base64
import json
import jwt
import hashlib

from datetime import datetime
from datetime import timedelta
from enum import Enum
from typing import Any
from flo_cloud._types import FloKMS


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
        private_key: str,
        public_key: str,
        kms_service: FloKMS,
        algorithm: TokenAlgorithms = TokenAlgorithms.PS256,
        token_expiry: int = 4 * 60 * 60,  # 4 hours in seconds
        temporary_token_expiry: int = 10 * 60,  # 10 minutes in seconds
        app_env: str = 'production',
        issuer: str = 'https://floware.rootflo.ai',
        audience: str = 'https://floware.rootflo.ai',
    ):
        self.is_dev = app_env == 'dev' or (kms_service is None)
        self.private_key = self._load_key(private_key)
        self.public_key = self._load_key(public_key)
        self.algorithm = TokenAlgorithms.RS256.value if self.is_dev else algorithm.value
        self.token_expiry = int(token_expiry)
        self.temporary_token_expiry = int(temporary_token_expiry)
        self.kms_service = kms_service
        self.issuer = issuer
        self.audience = audience

    def _load_key(self, key: str):
        key = base64.b64decode(key).decode('ascii')
        return key

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

        if self.is_dev:
            return jwt.encode({**data}, self.private_key, algorithm=self.algorithm)
        else:
            header = {'alg': self.algorithm, 'typ': 'JWT'}

            header_b64 = self._base64url_encode(json.dumps(header).encode())
            payload_b64 = self._base64url_encode(json.dumps(data).encode())
            message = f'{header_b64}.{payload_b64}'

            digest = hashlib.sha256(message.encode()).digest()

            signature = self.kms_service.sign(message=digest)
            signature = self._base64url_encode(signature)

            return f'{message}.{signature}'

    def decode_token(self, token: str) -> dict:
        if self.is_dev:
            decoded = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
            )
            return decoded
        else:
            header_b64, payload_b64, signature_b64 = token.split('.')

            message = f'{header_b64}.{payload_b64}'
            digest = hashlib.sha256(message.encode()).digest()
            signature = self._base64url_decode(signature_b64)

            is_valid = self.kms_service.verify(message=digest, signature=signature)
            if not is_valid:
                return {}

            public_key_pem = self.kms_service.get_public_key_pem()

            decoded = jwt.decode(
                token,
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
