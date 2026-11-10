"""
Tests for run_blocking, the datasource thread pool
"""

import asyncio
import contextvars
import threading

import pytest
from datasource import executor
from datasource.executor import run_blocking

request_id = contextvars.ContextVar('request_id', default=None)


@pytest.mark.asyncio
async def test_returns_result_and_passes_arguments():
    assert await run_blocking(lambda a, b=0: a + b, 2, b=3) == 5


@pytest.mark.asyncio
async def test_raises_the_callable_exception():
    def fail():
        raise ValueError('boom')

    with pytest.raises(ValueError, match='boom'):
        await run_blocking(fail)


@pytest.mark.asyncio
async def test_runs_on_a_datasource_thread_not_the_loop():
    name = await run_blocking(lambda: threading.current_thread().name)

    assert name.startswith('datasource')
    assert name != threading.current_thread().name


@pytest.mark.asyncio
async def test_carries_context_variables_to_the_thread():
    request_id.set('req-1')

    assert await run_blocking(request_id.get) == 'req-1'


def test_works_from_separate_event_loops():
    # Scheduled jobs call the plugins through asyncio.run on another thread,
    # so the pool must not be tied to one loop.
    results = []

    def other_loop():
        results.append(asyncio.run(run_blocking(lambda: 'scheduler')))

    worker = threading.Thread(target=other_loop)
    worker.start()
    results.append(asyncio.run(run_blocking(lambda: 'request')))
    worker.join()

    assert sorted(results) == ['request', 'scheduler']


async def _drain_queue():
    """Return once every call queued before this one has been taken or skipped."""
    token = executor.queue_wait_limit.set(None)
    try:
        await run_blocking(lambda: None)
    finally:
        executor.queue_wait_limit.reset(token)


@pytest.fixture
def busy_pool():
    """Occupy every datasource thread until the test releases them."""
    release = threading.Event()
    started = threading.Barrier(executor.DATASOURCE_MAX_THREADS + 1, timeout=5)

    def hold():
        started.wait()
        release.wait()

    futures = [
        executor._executor.submit(hold) for _ in range(executor.DATASOURCE_MAX_THREADS)
    ]
    started.wait()
    try:
        yield release
    finally:
        release.set()
        for future in futures:
            future.result()


@pytest.mark.asyncio
async def test_refuses_without_running_when_all_threads_stay_busy(
    busy_pool, monkeypatch
):
    monkeypatch.setattr(executor, 'DATASOURCE_MAX_QUEUE_WAIT_SECONDS', 0.05)
    calls = []

    with pytest.raises(executor.DatasourceBusyError):
        await run_blocking(calls.append, 'ran')

    busy_pool.set()
    await _drain_queue()
    assert calls == []


@pytest.mark.asyncio
async def test_no_wait_limit_waits_for_a_thread(busy_pool, monkeypatch):
    monkeypatch.setattr(executor, 'DATASOURCE_MAX_QUEUE_WAIT_SECONDS', 0.05)
    token = executor.queue_wait_limit.set(None)
    try:
        pending = asyncio.ensure_future(run_blocking(lambda: 'done'))
        await asyncio.sleep(0.2)
        assert not pending.done()

        busy_pool.set()
        assert await pending == 'done'
    finally:
        executor.queue_wait_limit.reset(token)


@pytest.mark.asyncio
async def test_cancelled_caller_drops_its_queued_call(busy_pool):
    calls = []

    pending = asyncio.ensure_future(run_blocking(calls.append, 'ran'))
    await asyncio.sleep(0.05)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    busy_pool.set()
    await _drain_queue()
    assert calls == []
