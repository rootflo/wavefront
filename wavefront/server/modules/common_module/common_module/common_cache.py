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
    def remove(self, key: str) -> bool:
        pass
