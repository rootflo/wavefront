"""A per-process cap on Sentry events, by source and in total.

Error-level logs are the main source of events, and some fire on every
request or every retry during an outage (a Redis blip, a scanner hitting
auth). Without a cap, one incident can use the month's quota and make the
SDK back off, dropping the next real error. The cost is also paid on the
logging thread, usually the event loop: the SDK builds each event before
``before_send`` sees it.

The cap has two parts, both per minute and per process:

- at most ``PER_SOURCE_PER_MINUTE`` events from one source (a log call site,
  or the innermost frame of an exception);
- at most ``per_minute`` events in total.

Log events are capped by a logging filter on the SDK's event handler, so a
dropped log never becomes an event. Other events (exceptions captured by
framework integrations, ``capture_message``) are capped in ``before_send``.
The first event from a source after a drop carries ``sentry_throttled``: how
many were dropped since that source's last event.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Hashable

PER_SOURCE_PER_MINUTE = 5
_WINDOW_SECONDS = 60.0
# Sources are code locations, so the set is bounded; this is a backstop.
_MAX_SOURCES = 2000

_lock = threading.Lock()
_active: EventThrottle | None = None


class EventThrottle:
    """Fixed one-minute windows, per source and in total. Thread-safe."""

    def __init__(
        self, per_minute: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._window_started = clock()
        self._total = 0
        self._counts: dict[Hashable, int] = {}
        self._dropped: dict[Hashable, int] = {}

    def allow(self, source: Hashable) -> tuple[bool, int]:
        """(allowed, dropped since this source's last allowed event)."""
        with self._lock:
            now = self._clock()
            if now - self._window_started >= _WINDOW_SECONDS:
                self._window_started = now
                self._total = 0
                self._counts.clear()
            if len(self._dropped) > _MAX_SOURCES:
                self._dropped.clear()
            count = self._counts.get(source, 0)
            if count >= PER_SOURCE_PER_MINUTE or self._total >= self._per_minute:
                self._dropped[source] = self._dropped.get(source, 0) + 1
                return False, 0
            self._counts[source] = count + 1
            self._total += 1
            return True, self._dropped.pop(source, 0)


class LogThrottleFilter(logging.Filter):
    """Caps log events per call site. Attach to the SDK's event handler only."""

    def filter(self, record: logging.LogRecord) -> bool:
        throttle = _active
        if throttle is None:
            return True
        allowed, dropped = throttle.allow(
            ('log', record.name, record.pathname, record.lineno)
        )
        if allowed and dropped:
            # Non-standard record attributes become the event's `extra`.
            record.sentry_throttled = dropped
        return allowed


def configure(per_minute: int) -> None:
    global _active
    with _lock:
        _active = EventThrottle(per_minute)


def reset() -> None:
    global _active
    with _lock:
        _active = None


def allow_event(event: dict[str, Any], hint: dict[str, Any] | None) -> bool:
    """The ``before_send`` backstop for events that do not come from a log."""
    throttle = _active
    if throttle is None or (hint and hint.get('log_record') is not None):
        return True
    allowed, dropped = throttle.allow(_event_source(event, hint))
    if allowed and dropped:
        extra = event.setdefault('extra', {})
        if isinstance(extra, dict):
            extra['sentry_throttled'] = dropped
    return allowed


def _event_source(event: dict[str, Any], hint: dict[str, Any] | None) -> Hashable:
    exc_info = (hint or {}).get('exc_info')
    if exc_info and len(exc_info) > 2 and exc_info[2] is not None:
        tb = exc_info[2]
        while tb.tb_next is not None:
            tb = tb.tb_next
        code = tb.tb_frame.f_code
        return ('exc', exc_info[0].__name__, code.co_filename, tb.tb_lineno)
    fingerprint = event.get('fingerprint')
    if isinstance(fingerprint, list) and fingerprint:
        return ('fingerprint', *map(str, fingerprint))
    return ('message', str(event.get('logger')), str(event.get('message'))[:200])
