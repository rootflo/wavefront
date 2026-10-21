from google.cloud import kms
from google.cloud import kms_v1
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils

from .._types import KmsKeySettings


def _require_key_path(settings: KmsKeySettings) -> tuple[str, str, str, str]:
    project_id = settings.project_id
    region = settings.region
    key_ring = settings.key_ring
    key = settings.key
    if not (project_id and region and key_ring and key):
        raise ValueError(
            'project_id, region (GCP KMS location), key_ring, and key must be set '
            'for GcpKMS'
        )
    return project_id, region, key_ring, key


class GcpKmsCipher:
    """GCP KMS encrypt/decrypt bound to a crypto key."""

    def __init__(self, settings: KmsKeySettings):
        project_id, region, key_ring, key = _require_key_path(settings)
        self.kms_client = kms.KeyManagementServiceClient()
        self.enc_key_name = self.kms_client.crypto_key_path(
            project=project_id,
            location=region,
            key_ring=key_ring,
            crypto_key=key,
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


class GcpKmsSigner:
    """GCP KMS asymmetric sign/verify bound to a crypto key version."""

    def __init__(self, settings: KmsKeySettings):
        project_id, region, key_ring, key = _require_key_path(settings)
        key_version = settings.key_version
        if not key_version:
            raise ValueError('key_version must be set for GcpKmsSigner')

        self.kms_client = kms.KeyManagementServiceClient()
        self.key_name = self.kms_client.crypto_key_version_path(
            project=project_id,
            location=region,
            key_ring=key_ring,
            crypto_key=key,
            crypto_key_version=key_version,
        )

    def sign(self, message: bytes, **kwargs) -> bytes:
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
        encode = kwargs.get('encode', False)
        request = kms_v1.GetPublicKeyRequest(
            name=self.key_name,
        )
        public_key = self.kms_client.get_public_key(request=request)
        if encode:
            return public_key.pem.encode('utf-8')
        return public_key.pem
