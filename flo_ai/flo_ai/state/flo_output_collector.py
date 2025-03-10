from enum import Enum
from abc import ABC, abstractmethod


class CollectionStatus(Enum):
    success = 'success'
    partial = 'partial'
    error = 'error'


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
