from abc import ABC, abstractmethod
from typing import Optional


class FloSigner(ABC):
    @abstractmethod
    def sign(self, message: bytes, **kwargs) -> bytes:
        pass

    @abstractmethod
    def verify(self, message: bytes, signature: bytes, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_public_key_pem(self, **kwargs) -> bytes | str:
        pass


class FloCipher(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str | bytes) -> bytes:
        """Encrypt plaintext. Returns raw ciphertext bytes."""

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt raw ciphertext bytes. Returns plaintext bytes."""

    @abstractmethod
    def encrypt_for_storage(self, plaintext: Optional[str]) -> Optional[str]:
        """Encrypt a secret for a DB Text column (base64-encoded ciphertext)."""

    @abstractmethod
    def decrypt_from_storage(self, stored: Optional[str]) -> Optional[str]:
        """Decrypt a secret previously stored via `encrypt_for_storage`."""


# Backward-compatible alias used by call sites that still type against FloKMS.
FloKMS = FloSigner
