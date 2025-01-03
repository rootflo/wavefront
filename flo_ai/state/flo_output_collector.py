from abc import ABC, abstractmethod


class FloOutputCollector(ABC):
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
