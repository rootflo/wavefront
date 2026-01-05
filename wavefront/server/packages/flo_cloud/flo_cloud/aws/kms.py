import os
import boto3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from .._types import FloKMS

aws_kms_arn = os.getenv('AWS_KMS_ARN')
aws_region = os.getenv('AWS_REGION')


class AwsKMS(FloKMS):
    def __init__(self):
        if not all([aws_region, aws_kms_arn]):
            raise ValueError('Region and KMS ARN must be set')

        self.aws_kms_arn = aws_kms_arn
        self.aws_region = aws_region
        self.kms_client = boto3.client('kms', region_name=aws_region)

    def encrypt(self, plaintext: str) -> bytes:
        return self.kms_client.encrypt(KeyId=self.aws_kms_arn, Plaintext=plaintext)

    def decrypt(self, ciphertext: str) -> bytes:
        return self.kms_client.decrypt(
            KeyId=self.aws_kms_arn, CiphertextBlob=ciphertext
        )

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
