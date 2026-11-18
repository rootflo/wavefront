"""Bounded thread pools for blocking calls made from async code.

Some SDKs we depend on are synchronous: KMS signing and key fetches, cloud
object storage, and CPU-heavy work such as bcrypt. Called straight from an
``async def`` they run on the event loop and every other request in the worker
waits. ``run_in_pool`` moves such a call onto a thread from a named pool:

    token = await run_in_pool('kms', signer.sign, message=digest)

Named pools rather than ``asyncio.to_thread``: the default executor is shared
with everything on the loop (DNS lookups included), so one slow dependency
could use up all its threads. Here a slow KMS can tie up at most the ``kms``
pool's threads. A call that can't get a thread within ``queue_wait_seconds`` is
refused with ``BlockingPoolBusyError`` (served as 503) instead of queueing
without limit.

Thread pools rather than an ``asyncio.Semaphore`` for the same reason as the
datasource pools (``datasource.executor``): scheduled jobs run on their own
event loop, and a semaphore binds to the first loop that waits on it. Those
pools are separate and unchanged; this module is for everything else.

Limits come from the app's config through ``configure_blocking_io`` (floware:
the ``[blocking_io]`` section of config.ini), called once at startup. Until
then, and in tests, the defaults in ``BlockingIoLimits`` apply.
"""

from __future__ import annotations

import asyncio
import contextvars
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, fields
from typing import Any, Callable, Dict, Literal, Mapping, Optional, TypeVar

from opentelemetry import metrics

from common_module.log.logger import logger

T = TypeVar('T')
PoolName = Literal['kms', 'storage', 'cpu']
POOL_NAMES: tuple[PoolName, ...] = ('kms', 'storage', 'cpu')


@dataclass(frozen=True)
class BlockingIoLimits:
    # KMS: token signing on login, public-key fetches (rare once cached).
    kms_max_threads: int = 8
    # Object storage reads and writes (YAML, images, presigned URLs).
    storage_max_threads: int = 16
    # CPU-bound work that releases the GIL, e.g. bcrypt. Keep near the core count.
    cpu_max_threads: int = 4
    # How long a call may wait for a free thread before it is refused.
    queue_wait_seconds: float = 10.0

    def max_threads(self, pool: PoolName) -> int:
        return getattr(self, f'{pool}_max_threads')


class BlockingPoolBusyError(RuntimeError):
    """No thread in the pool became free within the queue wait limit."""

    def __init__(self, pool: str, wait_seconds: float):
        super().__init__(f'No {pool} thread became free within {wait_seconds:g}s')
        self.pool = pool
        self.wait_seconds = wait_seconds


_limits = BlockingIoLimits()
_pools: Dict[str, ThreadPoolExecutor] = {}
_pools_lock = threading.Lock()

_meter = metrics.get_meter(__name__)
_active = _meter.create_up_down_counter(
    'blocking_io.pool.active',
    unit='{call}',
    description='Calls running on a blocking-I/O pool thread.',
)
_queued = _meter.create_up_down_counter(
    'blocking_io.pool.queued',
    unit='{call}',
    description='Calls waiting for a blocking-I/O pool thread.',
)
_rejected = _meter.create_counter(
    'blocking_io.pool.rejected',
    unit='{call}',
    description='Calls refused because no blocking-I/O pool thread became free in time.',
)


def configure_blocking_io(settings: Optional[Mapping[str, Any]]) -> BlockingIoLimits:
    """Set the limits from a config section (string values). Call before first use."""
    global _limits
    settings = settings or {}
    values = {}
    for field in fields(BlockingIoLimits):
        raw = settings.get(field.name)
        if raw in (None, ''):
            continue
        value = float(raw) if field.type in ('float', float) else int(raw)
        if value <= 0:
            raise ValueError(
                f'[blocking_io] {field.name} must be positive, got {raw!r}'
            )
        values[field.name] = value
    with _pools_lock:
        if _pools:
            logger.warning(
                'configure_blocking_io called after the pools were created; ignored'
            )
            return _limits
        _limits = BlockingIoLimits(**values)
    return _limits


def limits() -> BlockingIoLimits:
    return _limits


def _pool_for(pool: PoolName) -> ThreadPoolExecutor:
    if pool not in POOL_NAMES:
        raise ValueError(
            f'Unknown blocking-I/O pool {pool!r}; expected one of {POOL_NAMES}'
        )
    with _pools_lock:
        executor = _pools.get(pool)
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=_limits.max_threads(pool),
                thread_name_prefix=f'blocking-{pool}',
            )
            _pools[pool] = executor
        return executor


def shutdown_blocking_io() -> None:
    """Drop queued calls and stop the pools. Running calls finish in the background."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for executor in pools:
        executor.shutdown(wait=False, cancel_futures=True)


async def run_in_pool(
    pool: PoolName, fn: Callable[..., T], /, *args: Any, **kwargs: Any
) -> T:
    """Run ``fn(*args, **kwargs)`` on the named pool and await the result.

    Same contract as ``asyncio.to_thread``: context variables (trace context,
    request id) carry over, and exceptions raised by ``fn`` are raised here.
    Raises ``BlockingPoolBusyError``, without running ``fn``, when no thread
    frees up within ``queue_wait_seconds``.
    """
    executor = _pool_for(pool)  # validates the name before anything is counted
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    context = contextvars.copy_context()
    attributes = {'pool': pool}

    def call() -> T:
        _queued.add(-1, attributes)
        _active.add(1, attributes)
        try:
            try:
                loop.call_soon_threadsafe(started.set)
            except RuntimeError:
                pass  # The loop is gone; nobody is waiting for the signal.
            return context.run(fn, *args, **kwargs)
        finally:
            _active.add(-1, attributes)

    _queued.add(1, attributes)
    pending: Future = executor.submit(call)
    result = asyncio.wrap_future(pending)
    wait = _limits.queue_wait_seconds
    try:
        try:
            await asyncio.wait_for(started.wait(), timeout=wait)
        except asyncio.TimeoutError:
            # cancel() only succeeds while the call is still queued; once it has
            # started (even if the signal hasn't reached us yet), let it finish.
            if pending.cancel():
                _queued.add(-1, attributes)
                _rejected.add(1, attributes)
                raise BlockingPoolBusyError(pool, wait) from None
        return await result
    except asyncio.CancelledError:
        # The caller went away: drop the call if it is still queued.
        if pending.cancel():
            _queued.add(-1, attributes)
        raise


def retry_after_seconds() -> int:
    """Whole seconds for a Retry-After header on a BlockingPoolBusyError."""
    return max(1, math.ceil(_limits.queue_wait_seconds))
