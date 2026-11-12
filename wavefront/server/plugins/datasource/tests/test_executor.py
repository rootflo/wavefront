"""
Tests for run_blocking, the datasource thread pool
"""

import asyncio
import contextvars
import threading
import time

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

    assert name.startswith('datasource_')  # the request pool, not the scheduled one
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
    """Occupy every request-pool thread until the test releases them."""
    release = threading.Event()
    started = threading.Barrier(executor.DATASOURCE_MAX_THREADS + 1, timeout=5)

    def hold():
        started.wait()
        release.wait()

    futures = [
        executor._request_pool.submit(hold)
        for _ in range(executor.DATASOURCE_MAX_THREADS)
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


async def _in_scheduled_context(fn):
    """Run ``fn`` the way a scheduled report does, without touching this context."""
    context = contextvars.copy_context()
    context.run(executor.use_scheduled_limits)
    return await asyncio.create_task(run_blocking(fn), context=context)


@pytest.mark.asyncio
async def test_scheduled_calls_use_their_own_pool_and_limits():
    def settings():
        return (
            threading.current_thread().name,
            executor.queue_wait_limit.get(),
            executor.statement_timeout_limit.get(),
        )

    name, wait, statement = await _in_scheduled_context(settings)

    assert name.startswith('datasource-scheduled')
    assert wait is None
    assert statement == executor.DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS
    # The request context is untouched.
    assert executor.statement_timeout_limit.get() == (
        executor.DATASOURCE_STATEMENT_TIMEOUT_SECONDS
    )


@pytest.mark.asyncio
async def test_scheduled_calls_run_while_request_threads_are_busy(busy_pool):
    # Bounded, so a routing regression fails here instead of hanging the run.
    result = await asyncio.wait_for(_in_scheduled_context(lambda: 'report'), 5)

    assert result == 'report'


@pytest.mark.asyncio
async def test_batch_larger_than_the_pool_is_not_refused_by_its_own_calls(
    monkeypatch,
):
    monkeypatch.setattr(executor, 'DATASOURCE_MAX_QUEUE_WAIT_SECONDS', 0.2)
    count = executor.DATASOURCE_MAX_THREADS * 2
    lock = threading.Lock()
    running = {'now': 0, 'most': 0}

    def slow(i):
        with lock:
            running['now'] += 1
            running['most'] = max(running['most'], running['now'])
        time.sleep(0.3)  # longer than the wait limit
        with lock:
            running['now'] -= 1
        return i

    results = await executor.run_blocking_batch([(slow, (i,)) for i in range(count)])

    assert results == list(range(count))
    # One batch never takes more than half the pool, leaving room for others.
    assert running['most'] <= executor.DATASOURCE_MAX_THREADS // 2


@pytest.mark.asyncio
async def test_batch_returns_each_outcome_in_order():
    def fail():
        raise ValueError('bad query')

    results = await executor.run_blocking_batch(
        [(lambda: 'a', ()), (fail, ()), (lambda: 'c', ())]
    )

    assert results[0] == 'a'
    assert isinstance(results[1], ValueError)
    assert results[2] == 'c'


@pytest.mark.asyncio
async def test_refused_batch_runs_none_of_its_calls(busy_pool, monkeypatch):
    monkeypatch.setattr(executor, 'DATASOURCE_MAX_QUEUE_WAIT_SECONDS', 0.05)
    calls = []

    with pytest.raises(executor.DatasourceBusyError):
        await executor.run_blocking_batch(
            [(calls.append, ('first',)), (calls.append, ('second',))]
        )

    busy_pool.set()
    await _drain_queue()
    assert calls == []


@pytest.mark.asyncio
async def test_empty_batch_returns_nothing():
    assert await executor.run_blocking_batch([]) == []


@pytest.mark.asyncio
async def test_cancelled_batch_stops_queued_calls(busy_pool):
    calls = []

    pending = asyncio.ensure_future(
        executor.run_blocking_batch(
            [(calls.append, ('first',)), (calls.append, ('second',))]
        )
    )
    await asyncio.sleep(0.05)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    busy_pool.set()
    await _drain_queue()
    assert calls == []


@pytest.mark.parametrize(
    'raw, expected',
    [
        (None, 16),
        ('', 16),
        ('8', 8),
        ('8.0', 8),
        ('0', 16),
        ('-3', 16),
        ('lots', 16),
    ],
)
def test_env_limits_fall_back_on_values_that_are_not_positive(
    monkeypatch, raw, expected
):
    if raw is None:
        monkeypatch.delenv('TEST_DATASOURCE_LIMIT', raising=False)
    else:
        monkeypatch.setenv('TEST_DATASOURCE_LIMIT', raw)

    assert executor._env_positive('TEST_DATASOURCE_LIMIT', 16) == expected


def test_env_limits_keep_fractions_where_allowed(monkeypatch):
    monkeypatch.setenv('TEST_DATASOURCE_WAIT', '2.5')

    assert executor._env_positive('TEST_DATASOURCE_WAIT', 10.0, float) == 2.5
