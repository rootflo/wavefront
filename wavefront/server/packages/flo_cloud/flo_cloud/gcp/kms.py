from google.cloud import kms
from google.cloud import kms_v1
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils

from .._types import KmsKeySettings


class GcpKMS:
    """GCP KMS client bound to a single key from ``KmsKeySettings``."""

    def __init__(self, settings: KmsKeySettings):
        required = [
            settings.project_id,
            settings.location,
            settings.key_ring,
            settings.key,
        ]
        if not all(required):
            raise ValueError(
                'project_id, location, key_ring, and key must be set for GcpKMS'
            )

        self.kms_client = kms.KeyManagementServiceClient()
        self._key = settings.key
        self._key_version = settings.key_version
        self._project_id = settings.project_id
        self._location = settings.location
        self._key_ring = settings.key_ring

        # Versioned path for asymmetric signing; crypto-key path for encrypt/decrypt.
        self.key_name = (
            self.kms_client.crypto_key_version_path(
                project=settings.project_id,
                location=settings.location,
                key_ring=settings.key_ring,
                crypto_key=settings.key,
                crypto_key_version=settings.key_version,
            )
            if settings.key_version
            else None
        )
        self.enc_key_name = self.kms_client.crypto_key_path(
            project=settings.project_id,
            location=settings.location,
            key_ring=settings.key_ring,
            crypto_key=settings.key,
        )

    def encrypt(self, plaintext: bytes | str) -> bytes:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        request = kms_v1.EncryptRequest(
            name=self.enc_key_name,
            plaintext=plaintext,
        )
        response = self.kms_client.encrypt(request=request)
        return response.ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        request = kms_v1.DecryptRequest(
            name=self.enc_key_name,
            ciphertext=ciphertext,
        )
        response = self.kms_client.decrypt(request=request)
        return response.plaintext

    def sign(self, message: bytes, **kwargs) -> bytes:
        if not self.key_name:
            raise ValueError('key_version must be set to use signing')
        request = kms_v1.AsymmetricSignRequest(
            name=self.key_name,
            digest=kms_v1.Digest(
                sha256=message,
            ),
        )

        response = self.kms_client.asymmetric_sign(request=request)
        return response.signature

    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        public_key_pem: bytes | str = self.get_public_key_pem(encode=True)
        if isinstance(public_key_pem, str):
            raise ValueError('Public key is not a bytes object')
        rsa_key = serialization.load_pem_public_key(public_key_pem, default_backend())

        try:
            rsa_key.verify(  # type: ignore
                signature=signature,
                data=message,
                padding=padding.PSS(  # type: ignore
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                algorithm=utils.Prehashed(hashes.SHA256()),  # type: ignore
            )
            return True
        except InvalidSignature:
            return False

    def get_public_key_pem(self, **kwargs) -> bytes | str:
        if not self.key_name:
            raise ValueError('key_version must be set to use get_public_key_pem')
        encode = kwargs.get('encode', False)

        request = kms_v1.GetPublicKeyRequest(
            name=self.key_name,
        )
        public_key = self.kms_client.get_public_key(request=request)
        if encode:
            return public_key.pem.encode('utf-8')
        return public_key.pem
