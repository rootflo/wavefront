import json
import re
from typing import Dict, List, Any, Callable, Optional

from flo_ai.error.flo_exception import FloException
from flo_ai.common.flo_logger import get_logger
from flo_ai.state.flo_output_collector import FloOutputCollector, CollectionStatus


class FloJsonOutputCollector(FloOutputCollector):
    """
    FloJsonOutputCollector — collects JSON payloads from LLM/agent outputs,
    gracefully handles comments, and offers “Flo” Q-promise looping.
    Key Features:
      - Strips out // and /*…*/ comments before parsing
      - Uses recursive regex to find balanced { … } blocks
      - Strict mode: raises exception if no JSON found
      - peek, pop, fetch to manage collected data
      - rewind(): recursive promise-then replay, newest-first
      - iter_q(): while–for hybrid iterator over memory steps
    """

    def __init__(self, strict: bool = False):
        super().__init__()
        self.strict = strict  # Enforce JSON presence?
        self.status = CollectionStatus.success  # success, partial, or error
        self.data: List[Dict[str, Any]] = []  # Stored JSON dictionaries

    def append(self, agent_output: str) -> None:
        """Extracts JSON from `agent_output` and appends the resulting dict."""
        self.data.append(self.__extract_jsons(agent_output))

    def __strip_comments(self, json_str: str) -> str:
        """Remove JS-style comments (// and /*…*/) so json.loads() will succeed."""
        cleaned = []
        i = 0
        length = len(json_str)

        while i < length:
            char = json_str[i]

            if char not in '"/*':
                cleaned.append(char)
                i += 1
                continue

            if char == '"':
                cleaned.append(char)
                i += 1
                while i < length:
                    char = json_str[i]
                    cleaned.append(char)
                    i += 1
                    if char == '"' and (i < 2 or json_str[i - 2] != '\\'):
                        break
                continue

            if char == '/' and i + 1 < length:
                next_char = json_str[i + 1]
                if next_char == '/':
                    i += 2
                    while i < length and json_str[i] != '\n':
                        i += 1
                    continue
                elif next_char == '*':
                    i += 2
                    while i + 1 < length:
                        if json_str[i] == '*' and json_str[i + 1] == '/':
                            i += 2
                            break
                        i += 1
                    continue

            cleaned.append(char)
            i += 1

        return ''.join(cleaned)

    def __extract_jsons(self, llm_response: str) -> Dict[str, Any]:
        """
        1) Find all balanced `{ … }` blocks via recursive regex
        2) Strip comments and json.loads() each
        3) Merge into one dict (later keys override earlier)
        4) On strict mode, raise FloException if no JSON found
        """
        pattern = r'\{(?:[^{}]|(?R))*\}'
        matches = re.findall(pattern, llm_response)
        merged: Dict[str, Any] = {}

        for json_str in matches:
            try:
                cleaned = self.__strip_comments(json_str)
                obj = json.loads(cleaned)
                merged.update(obj)
            except json.JSONDecodeError as e:
                self.status = CollectionStatus.partial
                get_logger().error(f'Invalid JSON in response: {json_str}, {e}')

        if self.strict and not matches:
            self.status = CollectionStatus.error
            get_logger().error(f'No JSON found in strict mode: {llm_response}')
            raise FloException(
                'JSON response expected in collector model: strict', error_code=1099
            )

        return merged

    # ———————————————————————————————
    # Standard Data Management
    # ———————————————————————————————

    def pop(self) -> Dict[str, Any]:
        """Remove and return the last collected JSON dict."""
        return self.data.pop()

    def peek(self) -> Optional[Dict[str, Any]]:
        """View the last collected JSON dict without removing it."""
        return self.data[-1] if self.data else None

    def fetch(self) -> Dict[str, Any]:
        """Merge all collected dicts into one and return it."""
        return self.__merge_data()

    def __merge_data(self) -> Dict[str, Any]:
        """Helper method to merge all collected dicts."""
        merged = {}
        for d in self.data:
            merged.update(d)
        return merged

    # ———————————————————————————————
    # Flo Q-Promise Looping Methods
    # ———————————————————————————————

    def rewind(
        self,
        then_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        depth: Optional[int] = None
    ) -> None:
        """
        Recursively replay memory entries newest→oldest, invoking `then_callback` per step.
        Mirrors JS Promise.then chaining in reverse order.
        :param then_callback: function to handle each entry
        :param depth: max number of entries to process
        """
        if not self.data:
            get_logger().warn("No memory to rewind.")
            return

        entries = self.data[::-1]  # Reverse: newest first
        if depth:
            entries = entries[:depth]

        def _recursive(idx: int) -> None:
            if idx >= len(entries):
                return
            entry = entries[idx]
            if then_callback:
                then_callback(entry)
            _recursive(idx + 1)

        _recursive(0)

    def iter_q(self, depth: Optional[int] = None) -> "FloIterator":
        """
        Return a FloIterator that yields one-item lists of entries,
        enabling a while–for hybrid loop over memory steps.
        """
        return FloIterator(self, depth)


class FloIterator:
    """
    Hybrid while–for iterator over FloJsonOutputCollector data.
    Newest entries first, depth-limited.
    """

    def __init__(self, collector: FloJsonOutputCollector, depth: Optional[int] = None):
        self.entries = collector.data[::-1]
        self.limit = min(depth, len(self.entries)) if depth is not None else len(self.entries)
        self.index = 0

    def has_next(self) -> bool:
        """True if more entries remain."""
        return self.index < self.limit

    def next(self) -> List[Dict[str, Any]]:
        """
        Return the next “batch” of entries (here, a single-item list).
        Returns [] when exhausted.
        """
        if not self.has_next():
            return []
        entry = self.entries[self.index]
        self.index += 1
        return [entry]

    
