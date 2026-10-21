import threading
import time
from collections import deque
from typing import Callable, Deque, List, Optional, Tuple


class SlidingWindowRateLimiter:
    """In-process sliding-window rate limiter over one or more windows.

    A request is admitted only if every window has room for it. Limits are
    per process: the inference app runs a single worker, so this caps the
    load on its models, but each replica enforces its own limit.
    """

    def __init__(
        self,
        limits: List[Tuple[int, float]],
        clock: Callable[[], float] = time.monotonic,
    ):
        """
        Args:
            limits: (max_requests, window_seconds) pairs. A window with
                max_requests <= 0 is disabled.
            clock: Monotonic time source, injectable for tests.
        """
        self._windows: List[Tuple[int, float, Deque[float]]] = [
            (max_requests, window_seconds, deque())
            for max_requests, window_seconds in limits
            if max_requests > 0
        ]
        self._clock = clock
        self._lock = threading.Lock()

    def acquire(self) -> Optional[float]:
        """Admit and record a request if every window has room.

        Returns None when admitted, else the seconds until a slot frees up.
        A rejected request is not recorded, so it does not count against
        the limit.
        """
        with self._lock:
            now = self._clock()
            retry_after = 0.0
            for max_requests, window_seconds, timestamps in self._windows:
                while timestamps and timestamps[0] <= now - window_seconds:
                    timestamps.popleft()
                if len(timestamps) >= max_requests:
                    retry_after = max(retry_after, timestamps[0] + window_seconds - now)
            if retry_after > 0:
                return retry_after
            for _, _, timestamps in self._windows:
                timestamps.append(now)
            return None
