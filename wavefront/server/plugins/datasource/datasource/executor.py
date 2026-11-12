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

Every limit can be set through an environment variable of the same name. A value
that is not a positive number is ignored with a warning.
"""

import asyncio
import contextvars
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, List, Optional, Sequence, Tuple, TypeVar

T = TypeVar('T')

logger = logging.getLogger(__name__)


def _env_positive(name: str, default: float, cast: Callable[[float], Any] = int):
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        value = float(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            f'Ignoring {name}={raw!r}: not a positive number. Using {default}.'
        )
        return default
    return cast(value)


# Threads per process, so per uvicorn worker. Calls beyond these wait in the
# pool's queue.
DATASOURCE_MAX_THREADS = _env_positive('DATASOURCE_MAX_THREADS', 16)
DATASOURCE_SCHEDULED_MAX_THREADS = _env_positive('DATASOURCE_SCHEDULED_MAX_THREADS', 4)

# How long a request may wait for a free thread before it is refused with
# DatasourceBusyError, so that an overloaded worker answers "busy" quickly
# instead of holding requests open behind a slow datasource.
DATASOURCE_MAX_QUEUE_WAIT_SECONDS = _env_positive(
    'DATASOURCE_MAX_QUEUE_WAIT_SECONDS', 10.0, float
)

# Bounds on how long one call can hold a pool thread. The connect limit leaves
# room for databases that pause when idle and take a while to resume. Requests
# (UI reads, exports) get the short statement limit; scheduled reports get the
# long one, since a heavy report is expected to take a while and nobody is
# waiting on it interactively.
DATASOURCE_CONNECT_TIMEOUT_SECONDS = _env_positive(
    'DATASOURCE_CONNECT_TIMEOUT_SECONDS', 30
)
DATASOURCE_STATEMENT_TIMEOUT_SECONDS = _env_positive(
    'DATASOURCE_STATEMENT_TIMEOUT_SECONDS', 30
)
DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS = _env_positive(
    'DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS', 300
)

_request_pool = ThreadPoolExecutor(
    max_workers=DATASOURCE_MAX_THREADS, thread_name_prefix='datasource'
)
_scheduled_pool = ThreadPoolExecutor(
    max_workers=DATASOURCE_SCHEDULED_MAX_THREADS,
    thread_name_prefix='datasource-scheduled',
)

# How many of a pool's threads one batch (one dynamic query's sub-queries) may
# use at once: half, so a single large dashboard cannot occupy the whole pool
# and turn every other request away as busy.
_BATCH_CONCURRENCY = {
    _request_pool: max(1, DATASOURCE_MAX_THREADS // 2),
    _scheduled_pool: max(1, DATASOURCE_SCHEDULED_MAX_THREADS // 2),
}

_DEFAULT_WAIT = object()

# The pool that calls in the current context run on.
_pool: contextvars.ContextVar[ThreadPoolExecutor] = contextvars.ContextVar(
    'datasource_pool', default=_request_pool
)

# Overrides DATASOURCE_MAX_QUEUE_WAIT_SECONDS for the current context. None
# waits for a thread however long it takes.
queue_wait_limit: contextvars.ContextVar[Any] = contextvars.ContextVar(
    'datasource_queue_wait_limit', default=_DEFAULT_WAIT
)

# The statement limit for clients built in the current context. Plugins read it
# when they construct their client.
statement_timeout_limit: contextvars.ContextVar[int] = contextvars.ContextVar(
    'datasource_statement_timeout', default=DATASOURCE_STATEMENT_TIMEOUT_SECONDS
)


class DatasourceBusyError(RuntimeError):
    """No datasource thread became free within the queue wait limit."""


def use_scheduled_limits() -> None:
    """Switch the current context to the limits for scheduled reports.

    Calls run on the scheduled pool, wait for a thread however long it takes (a
    report should run late rather than not at all), and clients built afterwards
    get the long statement limit. Scheduled runs call this at the start of the
    coroutine ``asyncio.run`` drives, so it never reaches request contexts.
    """
    _pool.set(_scheduled_pool)
    queue_wait_limit.set(None)
    statement_timeout_limit.set(DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS)


def shutdown_pools() -> None:
    """Drop queued datasource calls at shutdown.

    Calls already running are left to finish within their driver timeouts; the
    interpreter still waits for them on exit.
    """
    for pool in (_request_pool, _scheduled_pool):
        pool.shutdown(wait=False, cancel_futures=True)


def _current_wait_limit() -> Optional[float]:
    limit = queue_wait_limit.get()
    return DATASOURCE_MAX_QUEUE_WAIT_SECONDS if limit is _DEFAULT_WAIT else limit


def _submit(pool: ThreadPoolExecutor, fn: Callable, args, kwargs) -> Future:
    return pool.submit(contextvars.copy_context().run, fn, *args, **kwargs)


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


async def _admit(pending: Future, result: asyncio.Future) -> None:
    """Wait until ``pending`` has a thread, or refuse it at the wait limit.

    Returns once the call has started or finished. Raises DatasourceBusyError
    after cancelling the call if it is still queued at the limit. cancel() only
    succeeds while the call is queued; once it runs, it is left to finish within
    the driver's own timeouts.
    """
    wait_limit = _current_wait_limit()
    done, _ = await asyncio.wait({result}, timeout=wait_limit)
    if not done and pending.cancel():
        raise DatasourceBusyError(
            f'No datasource thread became free within {wait_limit}s'
        )


async def run_blocking(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run ``fn(*args, **kwargs)`` on the datasource pool and await the result.

    Same contract as ``asyncio.to_thread``: context variables (trace context,
    request id) carry over to the thread, and exceptions raised by ``fn`` are
    raised here. Raises DatasourceBusyError, without running ``fn``, when no
    thread frees up within the queue wait limit.
    """
    pending = _submit(_pool.get(), fn, args, kwargs)
    result = asyncio.wrap_future(pending)
    try:
        await _admit(pending, result)
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
    calls run and DatasourceBusyError is raised. The rest are submitted only
    after that, wait for a thread however long it takes, and run at most half
    the pool's threads at a time, so a request with more calls than the pool has
    threads is neither refused because of its own calls nor able to crowd every
    other request out.

    Returns each call's result, or the exception it raised, in call order.
    """
    if not calls:
        return []
    pool = _pool.get()
    first_fn, first_args = calls[0]
    pending = [_submit(pool, first_fn, first_args, {})]
    wrappers = [asyncio.wrap_future(pending[0])]
    slots = asyncio.Semaphore(max(1, _BATCH_CONCURRENCY.get(pool, 1) - 1))
    others: List[asyncio.Task] = []

    async def run_one(fn, args):
        async with slots:
            future = _submit(pool, fn, args, {})
            pending.append(future)
            wrapper = asyncio.wrap_future(future)
            wrappers.append(wrapper)
            return await wrapper

    try:
        await _admit(pending[0], wrappers[0])
        others = [asyncio.ensure_future(run_one(fn, args)) for fn, args in calls[1:]]
        return await asyncio.gather(wrappers[0], *others, return_exceptions=True)
    except BaseException:
        # Refused, or the caller went away.
        for task in others:
            task.cancel()
        _abandon(pending, wrappers)
        raise
