from abc import ABC, abstractmethod


class FloParser(ABC):
    @abstractmethod
    def get_format_instructions(self):
        pass
