"""Event-loop lag monitor.

Async code that calls something blocking (sync Redis, KMS, storage, CPU work)
stops the event loop, and every other request in the worker waits. This
monitor measures how late the loop is and reports it:

- A heartbeat task sleeps for ``interval_ms`` and records how much later than
  that it woke up. Every lag goes to the ``python.asyncio.event_loop.lag``
  histogram; lags over ``threshold_ms`` also count in
  ``python.asyncio.event_loop.blocked``.
- A watchdog thread notices when the heartbeat is more than
  ``stack_threshold_ms`` overdue and captures the loop thread's stack, which
  says *what* is blocking, not just that something is.
- Each block over the threshold is logged (rate-limited) and handed to the
  listeners registered with ``add_loop_block_listener``. That is the hook a
  Sentry integration plugs into.

Listeners run on the watchdog thread, never on the event loop, so a slow
listener can't add lag of its own. They must not block for long, and any
exception they raise is logged and ignored.
"""

from __future__ import annotations

import asyncio
import math
import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from opentelemetry import metrics

from common_module.log.logger import logger

LAG_METRIC = 'python.asyncio.event_loop.lag'
BLOCKED_METRIC = 'python.asyncio.event_loop.blocked'
# Seconds. OTel's default buckets are sized for milliseconds, so they're set here.
_LAG_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30]
_STACK_FRAMES = 15


@dataclass(frozen=True)
class LoopBlockEvent:
    """One period during which the event loop was blocked."""

    lag_s: float  # how much later than planned the heartbeat woke up
    started_at: float  # time.monotonic() when the heartbeat went to sleep
    stack: Optional[
        str
    ]  # loop-thread stack captured mid-block, if it lasted long enough
    service: str


LoopBlockListener = Callable[[LoopBlockEvent], None]

_listeners: list[LoopBlockListener] = []
_listeners_lock = threading.Lock()


def add_loop_block_listener(listener: LoopBlockListener) -> None:
    """Call ``listener`` for every block over the threshold (on the watchdog thread)."""
    with _listeners_lock:
        _listeners.append(listener)


def remove_loop_block_listener(listener: LoopBlockListener) -> None:
    with _listeners_lock:
        if listener in _listeners:
            _listeners.remove(listener)


@dataclass(frozen=True)
class LoopMonitorSettings:
    enabled: bool = False  # opt-in: set [event_loop_monitor] enabled=true
    threshold_ms: float = 50
    interval_ms: float = 100
    stack_threshold_ms: float = 250
    log_cooldown_seconds: float = 30

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> 'LoopMonitorSettings':
        """Build from the ``[event_loop_monitor]`` config section (string values)."""
        raw = raw or {}
        defaults = cls()

        def number(name: str) -> float:
            value = raw.get(name)
            if value in (None, ''):
                return getattr(defaults, name)
            parsed = float(value)
            if not math.isfinite(parsed) or parsed <= 0:
                raise ValueError(
                    f'[event_loop_monitor] {name} must be finite and positive, got {value!r}'
                )
            return parsed

        enabled = raw.get('enabled')
        return cls(
            enabled=defaults.enabled
            if enabled in (None, '')
            else str(enabled).strip().lower() in ('1', 'true', 'yes'),
            threshold_ms=number('threshold_ms'),
            interval_ms=number('interval_ms'),
            stack_threshold_ms=number('stack_threshold_ms'),
            log_cooldown_seconds=number('log_cooldown_seconds'),
        )


class EventLoopMonitor:
    def __init__(
        self,
        settings: LoopMonitorSettings,
        service: str,
        meter_provider: Optional[metrics.MeterProvider] = None,
    ):
        self.settings = settings
        self.service = service
        meter = (meter_provider or metrics.get_meter_provider()).get_meter(__name__)
        self._lag = meter.create_histogram(
            LAG_METRIC,
            unit='s',
            description='How much later than scheduled the event-loop heartbeat ran.',
            explicit_bucket_boundaries_advisory=_LAG_BUCKETS,
        )
        self._blocked = meter.create_counter(
            BLOCKED_METRIC,
            unit='{block}',
            description=f'Event-loop lags over the threshold ({settings.threshold_ms:g} ms).',
        )
        self._attributes = {'process.pid': os.getpid()}

        self._interval_s = settings.interval_ms / 1000
        self._threshold_s = settings.threshold_ms / 1000
        self._stack_threshold_s = settings.stack_threshold_ms / 1000

        # Shared between the heartbeat (loop thread) and the watchdog thread.
        self._state_lock = threading.Lock()
        self._sleep_started: Optional[float] = None  # monotonic; None while awake
        self._beat = 0  # increments every heartbeat
        self._captured_beat = -1  # the beat whose block already has a stack
        self._captured_stack: Optional[str] = None

        self._events: 'queue.SimpleQueue[Optional[LoopBlockEvent]]' = (
            queue.SimpleQueue()
        )
        self._stop = threading.Event()
        self._task: Optional[asyncio.Task] = None
        self._watchdog: Optional[threading.Thread] = None
        self._loop_thread_id: Optional[int] = None

        self._last_log = float('-inf')
        self._suppressed = 0

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        """Start on the running event loop. Call from the loop's thread."""
        if self._task is not None:
            return
        if self._watchdog is not None and self._watchdog.is_alive():
            logger.warning('Event loop watchdog still running; monitor not restarted')
            return
        self._loop_thread_id = threading.get_ident()
        self._stop.clear()
        self._watchdog = threading.Thread(
            target=self._watch, name='event-loop-watchdog', daemon=True
        )
        self._watchdog.start()
        self._task = asyncio.get_running_loop().create_task(
            self._heartbeat(), name='event-loop-heartbeat'
        )
        logger.info(
            f'Event loop monitor started: threshold {self.settings.threshold_ms:g} ms, '
            f'interval {self.settings.interval_ms:g} ms, '
            f'stack after {self.settings.stack_threshold_ms:g} ms'
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass  # expected: we just cancelled the heartbeat
        except Exception as exc:
            # The heartbeat already failed (e.g. a broken meter): still stop the watchdog.
            logger.warning(f'Event loop heartbeat had failed before stop: {exc}')
        finally:
            self._task = None
            self._stop.set()
            self._events.put(None)  # wake the watchdog so it can exit
        watchdog = self._watchdog
        if watchdog is not None:
            # join() can wait on a slow log sink: keep it off the event loop.
            await asyncio.to_thread(watchdog.join, 2)
            if watchdog.is_alive():
                logger.warning('Event loop watchdog did not stop within 2s')
            else:
                self._watchdog = None

    # -- heartbeat (event loop) ------------------------------------------------

    async def _heartbeat(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            started = loop.time()
            with self._state_lock:
                self._sleep_started = time.monotonic()
                beat = self._beat
            await asyncio.sleep(self._interval_s)
            lag = max(0.0, loop.time() - started - self._interval_s)

            with self._state_lock:
                sleep_started = self._sleep_started
                self._sleep_started = None
                self._beat += 1
                stack = self._captured_stack if self._captured_beat == beat else None
                self._captured_stack = None

            self._lag.record(lag, self._attributes)
            if lag >= self._threshold_s:
                self._blocked.add(1, self._attributes)
                # The watchdog thread logs and calls listeners; the loop only enqueues.
                self._events.put(
                    LoopBlockEvent(
                        lag_s=lag,
                        started_at=sleep_started or time.monotonic(),
                        stack=stack,
                        service=self.service,
                    )
                )

    # -- watchdog (own thread) -------------------------------------------------

    def _watch(self) -> None:
        poll_s = max(0.01, min(self._interval_s, self._stack_threshold_s) / 4)
        while not self._stop.is_set():
            try:
                event = self._events.get(timeout=poll_s)
            except queue.Empty:
                event = None
            if event is not None:
                self._report(event)
            self._maybe_capture_stack()

    def _maybe_capture_stack(self) -> None:
        with self._state_lock:
            sleep_started = self._sleep_started
            beat = self._beat
            already = self._captured_beat == beat
        if sleep_started is None or already:
            return
        overdue = time.monotonic() - sleep_started - self._interval_s
        if overdue < self._stack_threshold_s:
            return
        stack = self._loop_stack()
        with self._state_lock:
            if self._beat == beat:  # still the same block
                self._captured_beat = beat
                self._captured_stack = stack

    def _loop_stack(self) -> Optional[str]:
        frame = sys._current_frames().get(self._loop_thread_id)
        if frame is None:
            return None
        frames = traceback.extract_stack(frame)[-_STACK_FRAMES:]
        return ''.join(traceback.format_list(frames))

    def _report(self, event: LoopBlockEvent) -> None:
        now = time.monotonic()
        if now - self._last_log >= self.settings.log_cooldown_seconds:
            extra = (
                f' ({self._suppressed} more since the last report)'
                if self._suppressed
                else ''
            )
            where = f'\nBlocked at:\n{event.stack}' if event.stack else ''
            logger.warning(
                f'Event loop blocked for {event.lag_s * 1000:.0f} ms{extra}{where}'
            )
            self._last_log = now
            self._suppressed = 0
        else:
            self._suppressed += 1

        with _listeners_lock:
            listeners = list(_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:  # a broken listener must not stop monitoring
                logger.error(f'Event loop block listener {listener!r} failed: {exc}')


def start_event_loop_monitor(
    config_section: Optional[Mapping[str, Any]], service: str
) -> Optional[EventLoopMonitor]:
    """Build and start the monitor from ``[event_loop_monitor]``; None if disabled."""
    settings = LoopMonitorSettings.from_mapping(config_section)
    if not settings.enabled:
        logger.info('Event loop monitor disabled ([event_loop_monitor] enabled=false)')
        return None
    monitor = EventLoopMonitor(settings, service)
    monitor.start()
    return monitor
