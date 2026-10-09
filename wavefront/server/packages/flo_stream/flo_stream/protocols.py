from typing import Any, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class RawQueueMessage(Protocol):
    """Minimal shape of a message returned by a queue receive call."""

    id: str
    ack_id: str
    body: Any


@runtime_checkable
class MessageQueueLike(Protocol):
    def receive_messages(
        self, max_messages: int = 10, wait_time_sec: int = 20
    ) -> List[RawQueueMessage]: ...

    def delete_message(self, ack_id: str) -> None: ...


@runtime_checkable
class CacheLike(Protocol):
    def get_int(self, key: str, default: int = 0) -> int: ...

    def get_str(self, key: str, default: Any = None) -> Optional[str]: ...

    def add(
        self, key: str, value: Any, expiry: int = 3600, nx: bool = False
    ) -> bool: ...

    def remove(self, key: str) -> bool: ...
