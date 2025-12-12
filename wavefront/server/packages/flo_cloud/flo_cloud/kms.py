from .aws.kms import AwsKMS
from .gcp.kms import GcpKMS
from ._types import CloudProvider, FloKMS


class FloKmsService(FloKMS):
    def __init__(self, cloud_provider: str):
        self.cloud_provider = cloud_provider
        self.kms_client = self.__get_kms_client()

    def __get_kms_client(self) -> FloKMS:
        if self.cloud_provider == CloudProvider.AWS.value:
            return AwsKMS()
        elif self.cloud_provider == CloudProvider.GCP.value:
            return GcpKMS()
        else:
            raise ValueError(f'Unsupported cloud provider: {self.cloud_provider}')

    def encrypt(self, plaintext: str) -> bytes:
        return self.kms_client.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> bytes:
        return self.kms_client.decrypt(ciphertext)

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
