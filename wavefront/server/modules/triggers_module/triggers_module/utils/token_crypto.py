import base64
from typing import Optional

from flo_cloud.kms import FloKmsService


class TokenCrypto:
    """Thin wrapper around `FloKmsService` for OAuth-token-at-rest encryption.

    Stores ciphertext as base64-encoded UTF-8 strings so it slots into a `Text`
    DB column. Returns plaintext as a UTF-8 string.
    """

    def __init__(self, kms_service: FloKmsService):
        self._kms = kms_service

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        if plaintext is None:
            return None
        # return plaintext #disabling use of kms for now

        ciphertext_bytes = self._kms.encrypt(plaintext)
        if not isinstance(ciphertext_bytes, (bytes, bytearray)):
            raise RuntimeError(
                f'KMS encrypt returned {type(ciphertext_bytes).__name__}, '
                'expected bytes'
            )
        return base64.b64encode(ciphertext_bytes).decode('utf-8')

    def decrypt(self, stored: Optional[str]) -> Optional[str]:
        if stored is None:
            return None
        # return stored #disabling use of kms for now

        ciphertext_bytes = base64.b64decode(stored.encode('utf-8'))
        plaintext_bytes = self._kms.decrypt(ciphertext_bytes)  # type: ignore[arg-type]
        if not isinstance(plaintext_bytes, (bytes, bytearray)):
            raise RuntimeError(
                f'KMS decrypt returned {type(plaintext_bytes).__name__}, '
                'expected bytes'
            )
        return plaintext_bytes.decode('utf-8')
