from abc import ABC, abstractmethod


class FloKMS(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str | bytes) -> bytes:
        """Encrypt plaintext. Returns raw ciphertext bytes."""

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt raw ciphertext bytes. Returns plaintext bytes."""

    @abstractmethod
    def sign(self, message: bytes, **kwargs) -> bytes:
        pass

    @abstractmethod
    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_public_key_pem(self, **kwargs) -> bytes | str:
        pass
