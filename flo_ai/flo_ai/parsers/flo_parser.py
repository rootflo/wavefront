from abc import ABC, abstractmethod
from pydantic import BaseModel


class FloParser(ABC):
    @abstractmethod
    def get_format_instructions(self):
        pass

    @abstractmethod
    def get_format(self) -> BaseModel:
        pass
