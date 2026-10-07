import boto3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from .._types import KmsKeySettings


def _kms_client(settings: KmsKeySettings):
    """Build a boto3 KMS client; region is optional (falls back to AWS env/defaults)."""
    if not settings.key:
        raise ValueError('key (KMS ARN) must be set for AwsKMS')
    region = (settings.region or '').strip() or None
    client_kwargs = {}
    if region is not None:
        client_kwargs['region_name'] = region
    return boto3.client('kms', **client_kwargs), settings.key, region


class AwsKmsCipher:
    """AWS KMS encrypt/decrypt bound to a single key ARN."""

    def __init__(self, settings: KmsKeySettings):
        self.kms_client, self.aws_kms_arn, self.aws_region = _kms_client(settings)

    def encrypt(self, plaintext: str | bytes) -> bytes:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        return self.kms_client.encrypt(KeyId=self.aws_kms_arn, Plaintext=plaintext)[
            'CiphertextBlob'
        ]

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self.kms_client.decrypt(
            KeyId=self.aws_kms_arn, CiphertextBlob=ciphertext
        )['Plaintext']


class AwsKmsSigner:
    """AWS KMS sign/verify bound to a single key ARN."""

    def __init__(self, settings: KmsKeySettings):
        self.kms_client, self.aws_kms_arn, self.aws_region = _kms_client(settings)

    def sign(self, message: bytes, **kwargs) -> bytes:
        signing_algorithm = kwargs.get('signing_algorithm', 'RSASSA_PSS_SHA_256')
        message_type = kwargs.get('message_type', 'DIGEST')

        response = self.kms_client.sign(
            KeyId=self.aws_kms_arn,
            Message=message,
            MessageType=message_type,
            SigningAlgorithm=signing_algorithm,
        )
        return response['Signature']

    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        signing_algorithm = kwargs.get('signing_algorithm', 'RSASSA_PSS_SHA_256')
        message_type = kwargs.get('message_type', 'DIGEST')

        response = self.kms_client.verify(
            KeyId=self.aws_kms_arn,
            Message=message,
            MessageType=message_type,
            Signature=signature,
            SigningAlgorithm=signing_algorithm,
        )
        return response['SignatureValid']

    def get_public_key_pem(self, **kwargs) -> str | bytes:
        response = self.kms_client.get_public_key(
            KeyId=self.aws_kms_arn,
        )
        public_key_der = response['PublicKey']
        public_key = serialization.load_der_public_key(
            public_key_der, default_backend()
        )

        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return pem_bytes.decode('utf-8')
