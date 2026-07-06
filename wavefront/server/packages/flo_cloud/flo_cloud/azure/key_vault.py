import os
from typing import Optional

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

from .._types import FloKMS


class AzureKMS(FloKMS):
    """Azure Key Vault implementation of FloKMS.

    Authentication modes (same as AzureBlobStorage):
    1. Service Principal — provide client_id, client_secret, tenant_id explicitly,
       or set AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID env vars.
    2. DefaultAzureCredential — falls back to Workload Identity, Managed Identity,
       Azure CLI, etc.

    Required env vars:
        AZURE_KEY_VAULT_URL       — e.g. https://my-vault.vault.azure.net/
        AZURE_KEY_VAULT_KEY_NAME  — name of the RSA key in the vault

    Optional env var:
        AZURE_KEY_VAULT_KEY_VERSION — specific key version; omit to use the latest
    """

    def __init__(
        self,
        vault_url: Optional[str] = None,
        key_name: Optional[str] = None,
        key_version: Optional[str] = None,
        enc_key_name: Optional[str] = None,
        enc_key_version: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        resolved_vault_url = vault_url or os.environ.get('AZURE_KEY_VAULT_URL')
        resolved_key_name = key_name or os.environ.get('AZURE_KEY_VAULT_KEY_NAME')
        resolved_key_version = key_version or os.environ.get(
            'AZURE_KEY_VAULT_KEY_VERSION'
        )
        resolved_enc_key_name = enc_key_name or os.environ.get(
            'AZURE_KEY_VAULT_ENC_KEY_NAME'
        )
        resolved_enc_key_version = enc_key_version or os.environ.get(
            'AZURE_KEY_VAULT_ENC_KEY_VERSION'
        )

        if not resolved_vault_url:
            raise ValueError(
                'vault_url must be provided or AZURE_KEY_VAULT_URL must be set'
            )
        if not resolved_key_name:
            raise ValueError(
                'key_name must be provided or AZURE_KEY_VAULT_KEY_NAME must be set'
            )

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

        self._key_name = resolved_key_name
        self._key_version = resolved_key_version
        self.key_client = KeyClient(vault_url=resolved_vault_url, credential=credential)

        sign_key = self.key_client.get_key(
            resolved_key_name, version=resolved_key_version
        )
        self.crypto_client = CryptographyClient(sign_key, credential=credential)

        self.enc_crypto_client = (
            CryptographyClient(
                self.key_client.get_key(
                    resolved_enc_key_name, version=resolved_enc_key_version
                ),
                credential=credential,
            )
            if resolved_enc_key_name
            else None
        )

    def encrypt(self, plaintext: str) -> bytes:
        if not self.enc_crypto_client:
            raise ValueError(
                'AZURE_KEY_VAULT_ENC_KEY_NAME must be set to use encryption'
            )
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        result = self.enc_crypto_client.encrypt(
            EncryptionAlgorithm.rsa_oaep_256, plaintext
        )
        return result.ciphertext

    def decrypt(self, ciphertext: str) -> bytes:
        if not self.enc_crypto_client:
            raise ValueError(
                'AZURE_KEY_VAULT_ENC_KEY_NAME must be set to use decryption'
            )
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode('utf-8')
        result = self.enc_crypto_client.decrypt(
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

        # Decode the JWK RSA public key components (big-endian bytes) to integers
        n = int.from_bytes(jwk.n, byteorder='big')
        e = int.from_bytes(jwk.e, byteorder='big')

        public_key = RSAPublicNumbers(e=e, n=n).public_key(default_backend())
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode('utf-8')
