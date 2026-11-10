"""A dedicated thread pool for blocking datasource calls.

The datasource drivers (psycopg2, redshift_connector, mssql_python, BigQuery,
the cloud storage SDKs) are synchronous. Called straight from an ``async def``
they run on the event loop and freeze every other request on that worker for as
long as the remote side takes to answer. ``run_blocking`` moves them onto a
thread instead.

The pool is ours rather than the loop's default executor so that a slow or
unreachable datasource can tie up at most ``DATASOURCE_MAX_THREADS`` threads:
the default executor is shared with everything else on the loop, DNS lookups
for outbound connections included. A thread pool rather than an
``asyncio.Semaphore`` because scheduled jobs call into the plugins from their
own event loop (``asyncio.run`` on the scheduler thread), and a semaphore binds
to the first loop that waits on it.
"""

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

T = TypeVar('T')

# Per process, so per uvicorn worker. Calls beyond this wait in the pool's queue.
DATASOURCE_MAX_THREADS = 8

# How long a call may wait for a free thread before it is refused with
# DatasourceBusyError, so that an overloaded worker answers "busy" quickly
# instead of holding requests open behind a slow datasource.
DATASOURCE_MAX_QUEUE_WAIT_SECONDS = 10

# Bounds on how long one call can hold a pool thread, for the SQL datasources
# whose clients support them. Requests (UI reads, exports) get the short
# statement limit; scheduled reports get the long one, since a heavy report is
# expected to take a while and nobody is waiting on it interactively.
DATASOURCE_CONNECT_TIMEOUT_SECONDS = 10
DATASOURCE_STATEMENT_TIMEOUT_SECONDS = 30
SCHEDULED_STATEMENT_TIMEOUT_SECONDS = 300

_executor = ThreadPoolExecutor(
    max_workers=DATASOURCE_MAX_THREADS, thread_name_prefix='datasource'
)

_DEFAULT_WAIT = object()

# Overrides DATASOURCE_MAX_QUEUE_WAIT_SECONDS for the current context. None
# waits for a thread however long it takes: scheduled jobs set that, since a
# report should run late rather than not at all.
queue_wait_limit: contextvars.ContextVar[Any] = contextvars.ContextVar(
    'datasource_queue_wait_limit', default=_DEFAULT_WAIT
)


# The statement limit for clients built in the current context. Plugins read it
# when they construct their client; scheduled jobs set the long limit.
statement_timeout_limit: contextvars.ContextVar[int] = contextvars.ContextVar(
    'datasource_statement_timeout', default=DATASOURCE_STATEMENT_TIMEOUT_SECONDS
)


class DatasourceBusyError(RuntimeError):
    """Every datasource thread stayed busy for the whole queue wait limit."""


def _current_wait_limit() -> Optional[float]:
    limit = queue_wait_limit.get()
    return DATASOURCE_MAX_QUEUE_WAIT_SECONDS if limit is _DEFAULT_WAIT else limit


async def run_blocking(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run ``fn(*args, **kwargs)`` on the datasource pool and await the result.

    Same contract as ``asyncio.to_thread``: context variables (trace context,
    request id) carry over to the thread, and exceptions raised by ``fn`` are
    raised here. Raises DatasourceBusyError, without running ``fn``, when no
    thread frees up within the queue wait limit.
    """
    pending = _executor.submit(contextvars.copy_context().run, fn, *args, **kwargs)
    result = asyncio.wrap_future(pending)
    wait_limit = _current_wait_limit()
    try:
        done, _ = await asyncio.wait({result}, timeout=wait_limit)
    except asyncio.CancelledError:
        # The caller went away: drop the call if it has not started yet.
        pending.cancel()
        raise
    # cancel() only succeeds while the call is still queued; once it is running
    # it is left to finish within the driver's own timeouts.
    if not done and pending.cancel():
        raise DatasourceBusyError(
            f'All {DATASOURCE_MAX_THREADS} datasource threads stayed busy for '
            f'{wait_limit}s'
        )
    return await result
