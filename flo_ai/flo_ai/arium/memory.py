from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Dict

# Define the generic type variable
T = TypeVar('T')


class BaseMemory(ABC, Generic[T]):
    @abstractmethod
    def add(self, m: T):
        pass

    def get(self) -> List[T]:
        pass


class MessageMemory(BaseMemory[Dict[str, str]]):
    def __init__(self):
        self.messages = []

    def add(self, message: Dict[str, str]):
        self.messages.append(message)

    def get(self) -> List[Dict[str, str]]:
        return self.messages
