import copy
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Dict, Optional, Any

from flo_ai.models import BaseMessage

# Define the generic type variable
T = TypeVar('T')


class MessageMemoryItem:
    def __init__(
        self,
        node: str,
        result: BaseMessage,
        occurrence: int = 0,
        retag: bool = True,
    ):
        """
        Args:
            node: Name of the node this result belongs to.
            result: The message itself.
            occurrence: Set by MessageMemory.add; how many times `node` has run.
            retag: Whether to overwrite an existing provenance tag on `result`.
                Pass False when the message is being *received* rather than
                produced — see below.
        """
        self.node: str = node
        self.occurrence: int = occurrence
        self.result: BaseMessage = self._tag(result, node, retag)

    @staticmethod
    def _tag(result: BaseMessage, node: str, retag: bool) -> BaseMessage:
        """Record the producing node on the message, returning what to store.

        The tag goes on the message itself, not just on this container, so that
        provenance survives being unwrapped from it. Arium hands nodes
        `[item.result for item in memory_items]`, and _flatten_results strips this
        wrapper whenever a sub-workflow or ForEach returns — a tag held only here
        would be lost in both cases. Downstream readers (e.g. the wavefront
        function-node adapter) use it to tell apart the outputs of several nodes
        selected by one input_filter.

        A message object is shared: passing a node's result into a sub-workflow
        puts the SAME BaseMessage into that sub-workflow's memory, and `run`
        hands its results back to the caller, who may feed them into another
        workflow. So reassigning a producer is done on a copy — the original
        keeps the tag whoever else holds it is relying on, and only this memory
        sees the new one. `retag=False` declines the reassignment altogether,
        marking an item that is merely receiving a message someone else made.
        """
        if not hasattr(result, 'metadata'):
            return result

        metadata = result.metadata or {}
        existing = metadata.get('node')

        if existing is None:
            # No producer to displace, so stamping in place loses nothing.
            result.metadata = {**metadata, 'node': node}
            return result

        if not retag or existing == node:
            return result

        tagged = copy.copy(result)
        tagged.metadata = {**metadata, 'node': node}
        return tagged

    def to_dict(self) -> Dict[str, Any]:
        return {
            'node': self.node,
            'occurrence': self.occurrence,
            'result': self.result,
        }


class BaseMemory(ABC, Generic[T]):
    @abstractmethod
    def add(self, message: T) -> None:
        pass

    @abstractmethod
    def get(self, include_nodes: Optional[List[str]] = None) -> List[T]:
        pass


class MessageMemory:
    def __init__(self):
        self.messages: List[MessageMemoryItem] = []
        self._node_occurrences: Dict[str, int] = {}

    def _next_occurrence(self, node: str) -> int:
        current = self._node_occurrences.get(node, 0) + 1
        self._node_occurrences[node] = current
        return current

    def add(self, message: MessageMemoryItem) -> None:
        # Update occurrence count for the node
        occurrence = self._next_occurrence(message.node)
        message.occurrence = occurrence
        self.messages.append(message)

    def get(self, include_nodes: Optional[List[str]] = None) -> List[MessageMemoryItem]:
        if not include_nodes:
            return self.messages
        include = set[str](include_nodes)
        return [m for m in self.messages if m.node in include]
