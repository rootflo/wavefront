"""Refuse new Celery work when the broker queue is over a depth limit."""

import asyncio
import threading
import time
from contextlib import contextmanager
from typing import Iterator, NamedTuple, Optional, Tuple

from celery import Celery
from common_module.log.logger import logger

from agents_module.utils.celery_settings import (
    DEFAULT_BACKPRESSURE_RETRY_AFTER_SECONDS,
    CeleryProducerSettings,
)


class QueueBackpressure(Exception):
    """The broker queue is over its limit.

    Not a ValueError: the controllers map ValueError to 422.
    """

    def __init__(
        self,
        depth: int,
        limit: int,
        retry_after: int = DEFAULT_BACKPRESSURE_RETRY_AFTER_SECONDS,
    ) -> None:
        super().__init__(
            f'Execution queue is saturated: {depth} tasks queued, limit {limit}'
        )
        self.depth = depth
        self.limit = limit
        self.retry_after = retry_after


class BrokerPoolExhausted(Exception):
    """No pooled broker connection was free for the depth probe."""


class _Reading(NamedTuple):
    depth: int
    measured_at: float

    @property
    def age(self) -> float:
        return time.monotonic() - self.measured_at


# How long the last reading is still used when a new one can't be taken.
_MAX_STALENESS_SECONDS = 30.0

_depth_lock = threading.Lock()
_reading: Optional[_Reading] = None


@contextmanager
def broker_connection(app: Celery, settings: CeleryProducerSettings) -> Iterator:
    """A pooled, connected broker connection, released on exit. Blocking."""
    timeout = settings.broker_socket_timeout_seconds
    try:
        conn = app.pool.acquire(block=True, timeout=timeout)
    except app.pool.LimitExceeded as exc:
        raise BrokerPoolExhausted(
            f'no broker connection free after {timeout}s: {exc}'
        ) from exc
    try:
        # Single attempt; kombu otherwise retries the connect for ~6s.
        conn.ensure_connection(max_retries=0)
        yield conn
    finally:
        conn.release()


def measure_queue_depth(app: Celery, settings: CeleryProducerSettings) -> int:
    """Ready tasks on the queue `app` publishes to. Blocking."""
    with broker_connection(app, settings) as conn:
        # passive=True would raise on an empty queue.
        queue = app.conf.task_default_queue
        return conn.default_channel.queue_declare(queue=queue).message_count


_probe_failing = False
_probe_failure_warned_at = float('-inf')


def _note_probe_failure(exc: Exception) -> None:
    """Log a failed probe at most once per staleness window."""
    global _probe_failing, _probe_failure_warned_at

    _probe_failing = True
    now = time.monotonic()
    if now - _probe_failure_warned_at < _MAX_STALENESS_SECONDS:
        return
    _probe_failure_warned_at = now
    logger.warning(
        f'Celery backpressure: queue-depth probe failed ({exc}); admission '
        f'keeps being decided on the last reading until it is '
        f'{_MAX_STALENESS_SECONDS:.0f}s old; after that work is enqueued '
        f'ungated until a probe succeeds.'
    )


def _note_probe_success() -> None:
    global _probe_failing, _probe_failure_warned_at

    if not _probe_failing:
        return
    _probe_failing = False
    _probe_failure_warned_at = float('-inf')
    logger.warning('Celery backpressure: queue-depth probe is working again.')


def _refresh_reading(app: Celery, settings: CeleryProducerSettings) -> None:
    """Probe and store the result. Caller holds _depth_lock."""
    global _reading

    try:
        depth = measure_queue_depth(app, settings)
    except Exception as exc:
        _note_probe_failure(exc)
        return

    _note_probe_success()
    _reading = _Reading(depth, time.monotonic())

    limit = settings.max_queue_depth
    if limit > 0 and depth >= limit * settings.queue_depth_warn_ratio:
        logger.warning(
            f'Celery backpressure: queue depth {depth} is at '
            f'{depth / limit:.0%} of the limit {limit}. '
            f'New executions are refused with 429 at the limit.'
        )


_ungated_warned_at = float('-inf')


def _warn_ungated(reading: _Reading) -> None:
    global _ungated_warned_at

    now = time.monotonic()
    if now - _ungated_warned_at < _MAX_STALENESS_SECONDS:
        return
    _ungated_warned_at = now
    logger.warning(
        f'Celery backpressure: no queue-depth reading for {reading.age:.0f}s '
        f'(last was {reading.depth}); enqueueing ungated until a probe succeeds.'
    )


def _fresh_reading(settings: CeleryProducerSettings) -> Optional[_Reading]:
    reading = _reading
    if reading is not None and reading.age < settings.queue_depth_cache_ttl_seconds:
        return reading
    return None


def _current_reading(
    app: Celery, settings: CeleryProducerSettings
) -> Optional[_Reading]:
    """The reading to decide on, or None to admit.

    Re-probes once the reading is past the cache TTL. If no new reading can be
    taken (probe failed, or another thread is probing), the last one is used
    until it is _MAX_STALENESS_SECONDS old.
    """
    fresh = _fresh_reading(settings)
    if fresh is not None:
        return fresh

    # Non-blocking: this runs on the shared to_thread pool, so callers must not
    # queue behind a slow probe.
    if _depth_lock.acquire(blocking=False):
        try:
            if _fresh_reading(settings) is None:
                _refresh_reading(app, settings)
        finally:
            _depth_lock.release()

    reading = _reading
    if reading is None:
        return None
    if reading.age > _MAX_STALENESS_SECONDS:
        _warn_ungated(reading)
        return None
    return reading


def _current_depth(app: Celery, settings: CeleryProducerSettings) -> Optional[int]:
    reading = _current_reading(app, settings)
    return None if reading is None else reading.depth


async def queue_is_saturated(
    app: Celery, settings: CeleryProducerSettings
) -> Tuple[bool, Optional[int]]:
    """Whether to refuse new work, plus the depth that decided it."""
    limit = settings.max_queue_depth
    if limit <= 0:
        return False, None

    reading = await asyncio.to_thread(_current_reading, app, settings)
    if reading is None:
        return False, None

    saturated = reading.depth >= limit
    if saturated:
        logger.warning(
            f'Celery backpressure: refusing work, queue depth {reading.depth} '
            f'is at or over the limit {limit} '
            f'(reading {reading.age:.1f}s old)'
        )
    return saturated, reading.depth


async def ensure_queue_capacity(app: Celery, settings: CeleryProducerSettings) -> None:
    """Raise QueueBackpressure if the broker queue is at or over its limit."""
    saturated, depth = await queue_is_saturated(app, settings)
    if saturated:
        raise QueueBackpressure(
            depth,
            settings.max_queue_depth,
            settings.backpressure_retry_after_seconds,
        )


def _reset_for_tests() -> None:
    global _reading, _ungated_warned_at
    global _probe_failing, _probe_failure_warned_at
    with _depth_lock:
        _reading = None
        _probe_failing = False
        _probe_failure_warned_at = float('-inf')
    _ungated_warned_at = float('-inf')
