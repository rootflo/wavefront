from abc import ABC
from abc import abstractmethod
from typing import Any, Optional, Union


class CommonCache(ABC):
    @abstractmethod
    def add(
        self,
        key: str,
        value: Union[str, int, float, bytes],
        expiry: int = 3600,
        nx: bool = False,
    ) -> bool:
        pass

    @abstractmethod
    def get_str(self, key: str, default: Any = None) -> Optional[str]:
        pass

    @abstractmethod
    def pop_str(self, key: str, default: Any = None) -> Optional[str]:
        """Atomically get-and-delete a string value (single-use consume)."""
        pass

    @abstractmethod
    def incr_with_expiry(self, key: str, expiry: int) -> int:
        """INCR a fixed-window counter, setting the TTL on the first hit."""
        pass

    @abstractmethod
    def remove(self, key: str) -> bool:
        pass
