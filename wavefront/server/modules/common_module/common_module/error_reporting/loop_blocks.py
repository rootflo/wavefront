"""Event-loop blocks as Sentry issues that name the code that blocked.

The loop monitor (``common_module.telemetry.loop_monitor``) measures how late
the event loop runs and, for long blocks, captures the loop thread's stack. It
calls registered listeners for every block over its threshold. This module is
that listener for Sentry:

- Only blocks with a captured stack are reported (over the monitor's
  ``stack_threshold_ms``); shorter ones stay in the OTel metrics.
- Events are grouped on the innermost workspace frame of the stack, as
  ``module.function`` without a line number, so a deploy that shifts lines
  does not open new issues. The monitor keeps only the innermost frames, so
  a stall deep inside an SDK (botocore, httpx) may show no workspace frame;
  it is then grouped on the outermost library in view (``library:botocore``),
  the one our code called into. Stacks with neither share one group.
- At most one event per group every ``GROUP_COOLDOWN_SECONDS``, and at most
  ``MAX_EVENTS_PER_HOUR`` per process across all groups, so a stall storm
  (Redis down, CPU throttling) cannot flood Sentry.
- Events are warnings: a block is slow code, not a crash.

The stack is a sample taken while the loop was blocked. A pause that is not
our code (garbage collection, CPU throttling) still shows whatever line was
running, so treat an issue as a lead, not proof.

Listeners run on the monitor's watchdog thread, never on the event loop.
``telemetry`` does not import this module; this module imports its hook.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import PurePath
from typing import Callable

from common_module.error_reporting import bootstrap
from common_module.log.logger import logger
from common_module.telemetry.loop_monitor import (
    LoopBlockEvent,
    add_loop_block_listener,
    remove_loop_block_listener,
)

GROUP_COOLDOWN_SECONDS = 600
MAX_EVENTS_PER_HOUR = 30
UNATTRIBUTED = 'unattributed'

# `traceback.format_list` lines: `  File "/path/x.py", line 12, in func`.
_FRAME_RE = re.compile(
    r'^\s*File "(?P<path>[^"]+)", line \d+, in (?P<function>\S+)', re.MULTILINE
)
# Frames of the monitor itself never explain a block.
_IGNORED_MODULES = ('common_module.telemetry.loop_monitor',)
_LIBRARY_DIRS = ('site-packages', 'dist-packages')

_lock = threading.Lock()
_reporter: LoopBlockReporter | None = None


def blocking_location(stack: str) -> str | None:
    """Where the loop was blocked, for grouping; None if nothing is recognisable.

    ``module.function`` of the innermost workspace frame, else
    ``library:<name>`` for the outermost third-party package in the stack.
    """
    frames = list(_FRAME_RE.finditer(stack))
    packages = set(bootstrap.WORKSPACE_PACKAGES)
    for match in reversed(frames):
        module = _workspace_module(match.group('path'), packages)
        if module and not module.startswith(_IGNORED_MODULES):
            return f'{module}.{match.group("function")}'
    for match in frames:
        library = _library(match.group('path'))
        if library:
            return f'library:{library}'
    return None


def _workspace_module(path: str, packages: set[str]) -> str | None:
    pure = PurePath(path)
    # Directories only: a file named like a package (flo_ai/utils/flo_utils.py)
    # is not that package.
    directories = pure.parts[:-1]
    # The last occurrence: `modules/common_module/common_module/x.py` names the
    # project directory and the package directory the same.
    for index in range(len(directories) - 1, -1, -1):
        if directories[index] in packages:
            return '.'.join((*directories[index:], pure.stem))
    return None


def _library(path: str) -> str | None:
    parts = PurePath(path).parts
    for index, part in enumerate(parts[:-1]):
        if part in _LIBRARY_DIRS:
            return PurePath(parts[index + 1]).stem
    return None


class LoopBlockReporter:
    """The listener. Callable with a ``LoopBlockEvent``; thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._last_sent: dict[str, float] = {}
        self._window_started: float | None = None
        self._sent_in_window = 0

    def __call__(self, event: LoopBlockEvent) -> None:
        if not event.stack:
            return
        location = blocking_location(event.stack)
        if not self._allow(location or UNATTRIBUTED):
            return
        self._send(event, location)

    def _allow(self, group: str) -> bool:
        with self._lock:
            now = self._clock()
            last = self._last_sent.get(group)
            if last is not None and now - last < GROUP_COOLDOWN_SECONDS:
                return False
            if self._window_started is None or now - self._window_started >= 3600:
                self._window_started = now
                self._sent_in_window = 0
            if self._sent_in_window >= MAX_EVENTS_PER_HOUR:
                return False
            self._sent_in_window += 1
            self._last_sent[group] = now
            return True

    def _send(self, event: LoopBlockEvent, location: str | None) -> None:
        import sentry_sdk

        lag_ms = round(event.lag_s * 1000)
        # The watchdog thread's scope collects unrelated breadcrumbs (start-up
        # warnings, the monitor's own "blocked" logs); this event needs none.
        with sentry_sdk.isolation_scope() as scope:
            scope.clear_breadcrumbs()
            sentry_sdk.get_current_scope().clear_breadcrumbs()
            sentry_sdk.capture_message(
                f'Event loop blocked for {lag_ms} ms in '
                f'{location or "unattributed code"}',
                level='warning',
                fingerprint=['event-loop-blocked', location or UNATTRIBUTED],
                tags={'event_loop.blocked': 'true'},
                extras={'lag_ms': lag_ms, 'stack': event.stack},
            )


def start_loop_block_reporting() -> bool:
    """Register the Sentry listener with the loop monitor.

    Call once the app has started, so blocking start-up work is not reported.
    Does nothing, and returns False, unless error reporting is running with
    ``report_loop_blocks`` on. Safe to call twice.
    """
    global _reporter
    settings = bootstrap.active_settings()
    if settings is None or not settings.report_loop_blocks:
        return False
    with _lock:
        if _reporter is None:
            _reporter = LoopBlockReporter()
            add_loop_block_listener(_reporter)
            logger.info('Event-loop blocks will be reported to Sentry')
    return True


def stop_loop_block_reporting() -> None:
    """Unregister the listener. Safe when it was never registered."""
    global _reporter
    with _lock:
        if _reporter is not None:
            remove_loop_block_listener(_reporter)
            _reporter = None
