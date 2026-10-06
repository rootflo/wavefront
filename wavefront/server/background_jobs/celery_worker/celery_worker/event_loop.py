"""Process-lifetime asyncio event loop for Celery worker tasks."""

import asyncio
import threading
from typing import Optional

from common_module.log.logger import logger

_loop_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None

# Per-phase ceiling on the shutdown drain, so teardown always terminates.
# Worst case is 3x this (grace, cancel-reap, asyncgens) and only occurs if a
# task ignores cancellation; the normal path finishes in milliseconds.
_LOOP_DRAIN_TIMEOUT_S = 5.0


def _drain_tasks(loop: asyncio.AbstractEventLoop, timeout: float) -> list:
    """Run pending tasks on `loop` for at most `timeout` seconds.

    Returns the tasks still unfinished. asyncio.wait() is used rather than
    gather() because it reports the timeout instead of raising, and never
    cancels on its own — phase 2 decides that explicitly.
    """
    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if not pending:
        return []

    try:
        loop.run_until_complete(asyncio.wait(pending, timeout=timeout))
    except Exception as exc:
        logger.warning(f'Error draining worker event loop: {exc}')

    return [t for t in pending if not t.done()]


def get_event_loop() -> asyncio.AbstractEventLoop:
    """One event loop for the lifetime of the worker process.

    Tasks used to create and close a loop per run. Because WorkerServices is a
    process-wide singleton built during the first task, every async client it
    holds stayed bound to that first loop — so later tasks ran against clients
    owned by a closed loop, and httpx AsyncClient.aclose() finalizers raised
    'Event loop is closed'. Sharing one loop keeps those clients and their
    connection pools valid for the whole process.
    """
    global _loop
    if _loop is not None and not _loop.is_closed():
        return _loop

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            # Set the thread default too, so library __del__ paths that call
            # get_event_loop() outside a running loop find a live one.
            asyncio.set_event_loop(_loop)

    return _loop


def close_event_loop() -> None:
    """Tear the shared loop down cleanly at worker-process shutdown."""
    global _loop
    if _loop is None or _loop.is_closed():
        return

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            return
        if _loop.is_running():
            # Under the solo pool tasks run in the main thread, so a shutdown
            # signal handler can land on top of a running task. Draining or
            # closing a running loop raises, and that exception would surface
            # inside the task. Leave it to process teardown instead.
            logger.warning(
                'Worker event loop still running at shutdown; skipping close'
            )
            return
        try:
            # Phase 1: let client finalizers (aclose() and friends) finish on
            # their own — that is the whole reason this drain exists.
            stragglers = _drain_tasks(_loop, _LOOP_DRAIN_TIMEOUT_S)

            # Phase 2: cancel and reap whatever is left. Tasks now outlive the
            # run that created them, so without this a single leaked task would
            # block worker shutdown indefinitely.
            if stragglers:
                for task in stragglers:
                    task.cancel()
                stragglers = _drain_tasks(_loop, _LOOP_DRAIN_TIMEOUT_S)

            if stragglers:
                logger.warning(
                    f'{len(stragglers)} task(s) ignored cancellation on the '
                    'worker event loop; closing anyway'
                )

            _loop.run_until_complete(
                asyncio.wait_for(
                    _loop.shutdown_asyncgens(), timeout=_LOOP_DRAIN_TIMEOUT_S
                )
            )
        except Exception as exc:
            logger.warning(f'Error draining worker event loop on shutdown: {exc}')
        finally:
            # Telemetry shutdown is handled by worker signals in signals.py,
            # not here — this function's contract is event-loop teardown.
            _loop.close()
            _loop = None
