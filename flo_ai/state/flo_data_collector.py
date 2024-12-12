from abc import ABC, abstractmethod


class FloDataCollector(ABC):
    @abstractmethod
    def append():
        pass

    @abstractmethod
    def fetch():
        pass

    @abstractmethod
    def peek():
        pass

    @abstractmethod
    def pop():
        pass
