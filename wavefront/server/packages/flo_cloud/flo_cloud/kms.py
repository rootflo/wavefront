import base64
from typing import Optional

from .aws.kms import AwsKMS
from .azure.key_vault import AzureKMS
from .exceptions import KmsError
from .gcp.kms import GcpKMS
from ._types import CloudProvider, FloCipher, FloSigner, KmsKeySettings


def _build_kms_client(settings: KmsKeySettings) -> AwsKMS | GcpKMS | AzureKMS:
    if settings.provider == CloudProvider.AWS.value:
        return AwsKMS(settings)
    elif settings.provider == CloudProvider.GCP.value:
        return GcpKMS(settings)
    elif settings.provider == CloudProvider.AZURE.value:
        return AzureKMS(settings)
    else:
        raise ValueError(f'Unsupported cloud provider: {settings.provider}')


class FloKmsSigner(FloSigner):
    def __init__(self, settings: KmsKeySettings):
        self.settings = settings
        self.kms_client = _build_kms_client(settings)

    def sign(self, message: bytes, **kwargs) -> bytes:
        if isinstance(message, str):
            message = message.encode('utf-8')
        return self.kms_client.sign(message, **kwargs)

    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        if isinstance(message, str):
            message = message.encode('utf-8')
        return self.kms_client.verify(message, signature, **kwargs)

    def get_public_key_pem(self, **kwargs) -> bytes | str:
        return self.kms_client.get_public_key_pem(**kwargs)


class FloKmsCipher(FloCipher):
    def __init__(self, settings: KmsKeySettings):
        self.settings = settings
        self.kms_client = _build_kms_client(settings)

    def encrypt(self, plaintext: str | bytes) -> bytes:
        """Encrypt plaintext. Returns raw ciphertext bytes (e.g. for blob storage)."""
        try:
            return self.kms_client.encrypt(plaintext)
        except KmsError:
            raise
        except Exception as e:
            raise KmsError('Failed to encrypt secret') from e

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt raw ciphertext bytes. Returns plaintext bytes."""
        try:
            return self.kms_client.decrypt(ciphertext)
        except KmsError:
            raise
        except Exception as e:
            raise KmsError('Failed to decrypt secret') from e

    def encrypt_for_storage(self, plaintext: Optional[str]) -> Optional[str]:
        """Encrypt a secret for a DB Text column (base64-encoded ciphertext)."""
        if plaintext is None:
            return None
        ciphertext = self.encrypt(plaintext)
        if not isinstance(ciphertext, (bytes, bytearray)):
            raise RuntimeError(
                f'KMS encrypt returned {type(ciphertext).__name__}, expected bytes'
            )
        return base64.b64encode(ciphertext).decode('utf-8')

    def decrypt_from_storage(self, stored: Optional[str]) -> Optional[str]:
        """Decrypt a secret previously stored via `encrypt_for_storage`."""
        if stored is None:
            return None
        ciphertext = base64.b64decode(stored.encode('utf-8'))
        plaintext = self.decrypt(ciphertext)
        if not isinstance(plaintext, (bytes, bytearray)):
            raise RuntimeError(
                f'KMS decrypt returned {type(plaintext).__name__}, expected bytes'
            )
        return plaintext.decode('utf-8')


# Deprecated alias — prefer FloKmsSigner / FloKmsCipher.
FloKmsService = FloKmsCipher
