"""Dedicated thread pools for blocking datasource calls.

The SQL datasource drivers (psycopg2, redshift_connector, mssql_python,
google-cloud-bigquery) and the cloud storage SDK used for dynamic-query YAML and
CSV exports are synchronous. Called straight from an ``async def`` they run on
the event loop and freeze every other request on that worker for as long as the
remote side takes to answer. ``run_blocking`` and ``run_blocking_batch`` move
them onto a thread instead. (The file-storage datasource routes deliberately
stay on ``asyncio.to_thread``: uploads and downloads have no time limit, so
they would otherwise tie up these pools.)

The pools are ours rather than the loop's default executor so that a slow or
unreachable datasource can tie up only a bounded number of threads: the default
executor is shared with everything else on the loop, DNS lookups for outbound
connections included. Thread pools rather than an ``asyncio.Semaphore`` because
scheduled jobs call into the plugins from their own event loop (``asyncio.run``
on the scheduler thread), and a semaphore binds to the first loop that waits on
it.

Requests and scheduled reports use separate pools, so a batch of heavy reports
cannot make the UI wait, and a busy UI cannot hold reports up.

The limits come from the app's config through ``configure_limits`` (floware:
the ``[datasource]`` section of its config.ini), called once at startup. Until
then, and in tests, the defaults in ``DatasourceLimits`` apply.
"""

import asyncio
import contextvars
import logging
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, fields
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

T = TypeVar('T')

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasourceLimits:
    # Threads per process, so per uvicorn worker. Calls beyond these wait in
    # the pool's queue.
    max_threads: int = 16
    scheduled_max_threads: int = 4
    # How long a request may wait for a free thread before it is refused with
    # DatasourceBusyError, so that an overloaded worker answers "busy" quickly
    # instead of holding requests open behind a slow datasource.
    queue_wait_seconds: float = 10.0
    # Bounds on how long one call can hold a thread. The connect limit leaves
    # room for databases that pause when idle and take a while to resume.
    # Requests (UI reads, exports) get the short statement limit; scheduled
    # reports get the long one, since a heavy report is expected to take a
    # while and nobody is waiting on it interactively.
    connect_timeout_seconds: int = 30
    statement_timeout_seconds: int = 30
    scheduled_statement_timeout_seconds: int = 300


_limits = DatasourceLimits()

_REQUEST = 'request'
_SCHEDULED = 'scheduled'
_pools: Dict[str, ThreadPoolExecutor] = {}
_pools_lock = threading.Lock()

_DEFAULT_WAIT = object()

# Which pool calls in the current context run on.
_lane: contextvars.ContextVar[str] = contextvars.ContextVar(
    'datasource_lane', default=_REQUEST
)

# Overrides the configured queue wait for the current context. None waits for a
# thread however long it takes.
queue_wait_limit: contextvars.ContextVar[Any] = contextvars.ContextVar(
    'datasource_queue_wait_limit', default=_DEFAULT_WAIT
)

# Overrides the configured statement limit for clients built in the current
# context. None means the configured request limit.
_statement_timeout: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    'datasource_statement_timeout', default=None
)


class DatasourceBusyError(RuntimeError):
    """No datasource thread became free within the queue wait limit."""


def _positive(name: str, raw: Any, default):
    if raw is None or str(raw).strip() == '':
        return default
    try:
        value = float(raw)
        # Convert first, then check: 0.5 threads would truncate to 0.
        converted = type(default)(value) if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        converted = None
    if converted is None or converted <= 0:
        logger.warning(
            f'Ignoring datasource {name}={raw!r}: not a positive number. '
            f'Using {default}.'
        )
        return default
    return converted


def configure_limits(settings: Mapping[str, Any]) -> DatasourceLimits:
    """Set the limits from the app's config, keyed by ``DatasourceLimits`` field.

    Missing keys keep their defaults, and a value that is not a positive number
    is ignored with a warning. Call it at startup, before the first datasource
    call: pools are sized when first used, so a later call cannot resize them.
    """
    global _limits
    defaults = DatasourceLimits()
    values = {
        field.name: _positive(
            field.name, settings.get(field.name), getattr(defaults, field.name)
        )
        for field in fields(DatasourceLimits)
    }
    with _pools_lock:
        if _pools:
            logger.warning(
                'Datasource limits were configured after the first datasource '
                'call; thread counts keep their earlier values.'
            )
        _limits = DatasourceLimits(**values)
    return _limits


def limits() -> DatasourceLimits:
    return _limits


def current_statement_timeout() -> int:
    """The statement limit for a client built now, in seconds."""
    override = _statement_timeout.get()
    return _limits.statement_timeout_seconds if override is None else override


def use_scheduled_limits() -> None:
    """Switch the current context to the limits for scheduled reports.

    Calls run on the scheduled pool, wait for a thread however long it takes (a
    report should run late rather than not at all), and clients built afterwards
    get the long statement limit. Scheduled runs call this at the start of the
    coroutine ``asyncio.run`` drives, so it never reaches request contexts.
    """
    _lane.set(_SCHEDULED)
    queue_wait_limit.set(None)
    _statement_timeout.set(_limits.scheduled_statement_timeout_seconds)


def _pool_size(lane: str) -> int:
    if lane == _SCHEDULED:
        return _limits.scheduled_max_threads
    return _limits.max_threads


def _pool_for(lane: str) -> ThreadPoolExecutor:
    pool = _pools.get(lane)
    if pool is None:
        with _pools_lock:
            pool = _pools.get(lane)
            if pool is None:
                prefix = 'datasource-scheduled' if lane == _SCHEDULED else 'datasource'
                pool = ThreadPoolExecutor(
                    max_workers=_pool_size(lane), thread_name_prefix=prefix
                )
                _pools[lane] = pool
    return pool


def shutdown_pools() -> None:
    """Drop queued datasource calls at shutdown.

    Calls already running are left to finish within their driver timeouts; the
    interpreter still waits for them on exit.
    """
    with _pools_lock:
        for pool in _pools.values():
            pool.shutdown(wait=False, cancel_futures=True)
        _pools.clear()


def _current_wait_limit() -> Optional[float]:
    limit = queue_wait_limit.get()
    return _limits.queue_wait_seconds if limit is _DEFAULT_WAIT else limit


def _submit(pool: ThreadPoolExecutor, fn: Callable, args, kwargs) -> Future:
    return pool.submit(contextvars.copy_context().run, fn, *args, **kwargs)


def _submit_signalling_start(
    pool: ThreadPoolExecutor, fn: Callable, args, kwargs
) -> Tuple[Future, asyncio.Event]:
    """Submit ``fn`` and return an event the loop sets as soon as a thread
    picks the call up, so admission can wait for the start, not the finish."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    context = contextvars.copy_context()

    def call():
        try:
            loop.call_soon_threadsafe(started.set)
        except RuntimeError:
            pass  # The loop is gone; nobody is waiting for the signal.
        return context.run(fn, *args, **kwargs)

    return pool.submit(call), started


def _abandon(pending: Sequence[Future], wrappers: Sequence[asyncio.Future]) -> None:
    """Drop calls that have not started and discard the outcome of the rest.

    The thread-pool futures are cancelled directly: cancelling only the asyncio
    wrappers would reach them a loop iteration later, long enough for a free
    thread to pick a call up. Exceptions already set on finished wrappers are
    retrieved so asyncio does not log them as never retrieved.
    """
    for future in pending:
        future.cancel()
    for wrapper in wrappers:
        if wrapper.done():
            if not wrapper.cancelled():
                wrapper.exception()
        else:
            wrapper.cancel()


async def _admit(pending: Future, started: asyncio.Event) -> None:
    """Wait until ``pending`` has a thread, or refuse it at the wait limit.

    Returns as soon as the call starts. Raises DatasourceBusyError after
    cancelling the call if it is still queued at the limit. cancel() only
    succeeds while the call is queued; once it runs (even if its start signal
    has not reached the loop yet), it is left to finish within the driver's own
    timeouts.
    """
    wait_limit = _current_wait_limit()
    try:
        await asyncio.wait_for(started.wait(), timeout=wait_limit)
    except asyncio.TimeoutError:
        if pending.cancel():
            raise DatasourceBusyError(
                f'No datasource thread became free within {wait_limit}s'
            ) from None


async def run_blocking(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run ``fn(*args, **kwargs)`` on the datasource pool and await the result.

    Same contract as ``asyncio.to_thread``: context variables (trace context,
    request id) carry over to the thread, and exceptions raised by ``fn`` are
    raised here. Raises DatasourceBusyError, without running ``fn``, when no
    thread frees up within the queue wait limit.
    """
    pending, started = _submit_signalling_start(
        _pool_for(_lane.get()), fn, args, kwargs
    )
    result = asyncio.wrap_future(pending)
    try:
        await _admit(pending, started)
        return await result
    except asyncio.CancelledError:
        # The caller went away: drop the call if it is still queued, and
        # discard its outcome if it is already running.
        _abandon([pending], [result])
        raise


async def run_blocking_batch(
    calls: Sequence[Tuple[Callable[..., Any], Tuple[Any, ...]]],
) -> List[Any]:
    """Run several blocking calls for one request concurrently.

    The queue wait limit applies to the request, not to each call: only the
    first call has to get a thread within it. If it is refused, none of the
    calls run and DatasourceBusyError is raised. The rest are submitted as soon
    as it starts (not when it finishes), wait for a thread however long it
    takes, and run at most half
    the pool's threads at a time, so a request with more calls than the pool has
    threads is neither refused because of its own calls nor able to crowd every
    other request out.

    Returns each call's result, or the exception it raised, in call order.
    """
    if not calls:
        return []
    lane = _lane.get()
    pool = _pool_for(lane)
    first_fn, first_args = calls[0]
    first, first_started = _submit_signalling_start(pool, first_fn, first_args, {})
    pending = [first]
    wrappers = [asyncio.wrap_future(first)]
    # Half the pool for the whole batch, the first call included.
    slots = asyncio.Semaphore(max(1, _pool_size(lane) // 2 - 1))
    others: List[asyncio.Task] = []

    async def run_one(fn, args):
        async with slots:
            future = _submit(pool, fn, args, {})
            pending.append(future)
            wrapper = asyncio.wrap_future(future)
            wrappers.append(wrapper)
            return await wrapper

    try:
        await _admit(first, first_started)
        others = [asyncio.ensure_future(run_one(fn, args)) for fn, args in calls[1:]]
        return await asyncio.gather(wrappers[0], *others, return_exceptions=True)
    except BaseException:
        # Refused, or the caller went away.
        for task in others:
            task.cancel()
        _abandon(pending, wrappers)
        raise
