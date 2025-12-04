import os
from .._types import FloKMS
from google.cloud import kms
from google.cloud import kms_v1

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils

gcp_project_id = os.getenv('GCP_PROJECT_ID')
gcp_location = os.getenv('GCP_LOCATION')
gcp_key_ring = os.getenv('GCP_KMS_KEY_RING')
gcp_crypto_key = os.getenv('GCP_KMS_CRYPTO_KEY')
gcp_crypto_key_version = os.getenv('GCP_KMS_CRYPTO_KEY_VERSION')


class GcpKMS(FloKMS):
    def __init__(self):
        if not all(
            [
                gcp_project_id,
                gcp_location,
                gcp_key_ring,
                gcp_crypto_key,
                gcp_crypto_key_version,
            ]
        ):
            raise ValueError(
                'PROJECT_ID, LOCATION, KEY_RING, CRYPTO_KEY, CRYPTO_KEY_VERSION must be set'
            )

        self.kms_client = kms.KeyManagementServiceClient()
        self.key_name = self.kms_client.crypto_key_version_path(
            project=gcp_project_id,
            location=gcp_location,
            key_ring=gcp_key_ring,
            crypto_key=gcp_crypto_key,
            crypto_key_version=gcp_crypto_key_version,
        )

    def encrypt(self, plaintext: str) -> bytes:
        request = kms_v1.EncryptRequest(
            name=self.key_name,
            plaintext=plaintext,
        )
        response = self.kms_client.encrypt(request=request)
        return response.ciphertext

    def decrypt(self, ciphertext: str) -> bytes:
        request = kms_v1.DecryptRequest(
            name=self.key_name,
            ciphertext=ciphertext,
        )
        response = self.kms_client.decrypt(request=request)
        return response.plaintext

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
