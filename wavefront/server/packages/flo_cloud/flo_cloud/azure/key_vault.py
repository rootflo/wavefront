from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.keys import KeyClient
from azure.keyvault.keys.crypto import (
    CryptographyClient,
    EncryptionAlgorithm,
    SignatureAlgorithm,
)
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

from .._types import KmsKeySettings


class AzureKMS:
    """Azure Key Vault client bound to a single key from ``KmsKeySettings``.

    Authentication modes:
    1. Service Principal — provide client_id, client_secret, tenant_id in settings.
    2. DefaultAzureCredential — when those three are omitted.
    """

    def __init__(self, settings: KmsKeySettings):
        if not settings.vault_url:
            raise ValueError('vault_url must be set for AzureKMS')
        if not settings.key:
            raise ValueError('key (Key Vault key name) must be set for AzureKMS')

        client_id = settings.client_id
        client_secret = settings.client_secret
        tenant_id = settings.tenant_id

        creds_provided = [client_id, client_secret, tenant_id]
        if all(creds_provided):
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        elif any(creds_provided):
            raise ValueError(
                'Partial credentials provided. Supply all of client_id, '
                'client_secret, and tenant_id, or none to use DefaultAzureCredential.'
            )
        else:
            credential = DefaultAzureCredential()

        self._key_name = settings.key
        self._key_version = settings.key_version
        self.key_client = KeyClient(vault_url=settings.vault_url, credential=credential)

        key = self.key_client.get_key(settings.key, version=settings.key_version)
        self.crypto_client = CryptographyClient(key, credential=credential)

    def encrypt(self, plaintext: str | bytes) -> bytes:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        result = self.crypto_client.encrypt(EncryptionAlgorithm.rsa_oaep_256, plaintext)
        return result.ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        result = self.crypto_client.decrypt(
            EncryptionAlgorithm.rsa_oaep_256, ciphertext
        )
        return result.plaintext

    def sign(self, message: bytes, **kwargs) -> bytes:
        algorithm = kwargs.get('signing_algorithm', SignatureAlgorithm.ps256)
        result = self.crypto_client.sign(algorithm, message)
        return result.signature

    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        algorithm = kwargs.get('signing_algorithm', SignatureAlgorithm.ps256)
        result = self.crypto_client.verify(algorithm, message, signature)
        return result.is_valid

    def get_public_key_pem(self, **kwargs) -> str | bytes:
        key = self.key_client.get_key(self._key_name, version=self._key_version)
        jwk = key.key

        n = int.from_bytes(jwk.n, byteorder='big')
        e = int.from_bytes(jwk.e, byteorder='big')

        public_key = RSAPublicNumbers(e=e, n=n).public_key(default_backend())
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode('utf-8')
