from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic
from dataclasses import dataclass
from typing import List
from flo_utils.streaming.event_message import BaseEventMessage

T = TypeVar('T')  # Type for insight


@dataclass
class ProcessingResult(Generic[T]):
    success: bool
    insights: Optional[T] = None
    error: Optional[str] = None


class MessageProcessor(ABC, Generic[T]):
    """Base class for all message processors"""

    @abstractmethod
    async def process(self, message: BaseEventMessage) -> ProcessingResult:
        pass

    @abstractmethod
    def store(self, insights: List[T], is_failed: bool = False) -> bool:
        """Store insights using appropriate repositories"""
        pass
