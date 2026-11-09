"""Process-local memo of config secrets (plaintext, never written to Redis)"""

import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

MemoKey = Tuple[str, str]


class SecretMemo:
    """Bounded LRU of (config_type, config_id) -> (updated_at, secrets), with a
    TTL per entry. Accessed from a single event loop, so it takes no lock.
    """

    def __init__(self, max_entries: int = 512, ttl_seconds: float = 3600):
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[MemoKey, Tuple[float, Any, Dict[str, Any]]] = (
            OrderedDict()
        )

    def get(self, key: MemoKey) -> Optional[Tuple[Any, Dict[str, Any]]]:
        """(updated_at, secrets) for `key`, or None if absent or expired"""
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, updated_at, secrets = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return updated_at, secrets

    def put(self, key: MemoKey, updated_at: Any, secrets: Dict[str, Any]) -> None:
        self._entries[key] = (time.monotonic() + self._ttl_seconds, updated_at, secrets)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
