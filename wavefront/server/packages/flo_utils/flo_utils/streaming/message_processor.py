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
        """Store insights using appropriate repositories.

        Return False to fail the whole batch. To fail only some messages, set
        success=False (and error) on their results and return True; the
        listener keeps those messages on the queue for retry.

        With is_failed=True the listener has given up on these messages after
        retry_count attempts: record the failure (results have success=False
        and error set) and return True once it is recorded. The listener only
        removes the messages from the queue after that returns True.
        """
        pass

    def failed_result(
        self, message: BaseEventMessage, error: str
    ) -> Optional[ProcessingResult]:
        """Build a failed ProcessingResult for a message that has none (e.g.
        process() timed out), so its failure can be passed to
        store(..., is_failed=True). Return None if there is nothing to record.
        """
        return None
