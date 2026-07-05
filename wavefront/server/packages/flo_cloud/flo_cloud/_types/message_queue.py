from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List


@dataclass
class MessageQueueDict:
    body: Any
    ack_id: str
    id: str


class MessageQueue(ABC):
    @abstractmethod
    def receive_messages(
        self, max_messages: int = 10, wait_time_sec: int = 20
    ) -> List[MessageQueueDict]:
        """
        Receive messages from the event queue.

        Returns:
            List of dicts, each with keys:
                - 'body': message content (any type)
                - 'ack_id': acknowledgement ID (str)
                - 'id': message ID (str)
            Empty list if no messages are available; never None.
        """
        pass

    @abstractmethod
    def delete_message(self, ack_id: str):
        pass

    @abstractmethod
    def add_message(
        self, message_body: dict, topic_name_or_queue_url: str | None = None
    ) -> str:
        pass
