from abc import ABC, abstractmethod


class FloKMS(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> bytes:
        pass

    @abstractmethod
    def decrypt(self, ciphertext: str) -> bytes:
        pass

    @abstractmethod
    def sign(self, message: bytes, **kwargs) -> bytes:
        pass

    @abstractmethod
    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_public_key_pem(self, **kwargs) -> bytes | str:
        pass
