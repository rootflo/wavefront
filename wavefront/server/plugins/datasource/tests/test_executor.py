"""
Tests for run_blocking, the datasource thread pool
"""

import asyncio
import contextvars
import dataclasses
import threading
import time

import pytest
from datasource import executor
from datasource.executor import run_blocking

request_id = contextvars.ContextVar('request_id', default=None)


def _set_queue_wait(monkeypatch, seconds):
    monkeypatch.setattr(
        executor,
        '_limits',
        dataclasses.replace(executor.limits(), queue_wait_seconds=seconds),
    )


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
    started = threading.Barrier(executor.limits().max_threads + 1, timeout=5)

    def hold():
        started.wait()
        release.wait()

    futures = [
        executor._pool_for('request').submit(hold)
        for _ in range(executor.limits().max_threads)
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
    _set_queue_wait(monkeypatch, 0.05)
    calls = []

    with pytest.raises(executor.DatasourceBusyError):
        await run_blocking(calls.append, 'ran')

    busy_pool.set()
    await _drain_queue()
    assert calls == []


@pytest.mark.asyncio
async def test_no_wait_limit_waits_for_a_thread(busy_pool, monkeypatch):
    _set_queue_wait(monkeypatch, 0.05)
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
            executor.current_statement_timeout(),
        )

    name, wait, statement = await _in_scheduled_context(settings)

    assert name.startswith('datasource-scheduled')
    assert wait is None
    assert statement == executor.limits().scheduled_statement_timeout_seconds
    # The request context is untouched.
    assert executor.current_statement_timeout() == (
        executor.limits().statement_timeout_seconds
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
    _set_queue_wait(monkeypatch, 0.2)
    count = executor.limits().max_threads * 2
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
    assert running['most'] <= executor.limits().max_threads // 2


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
    _set_queue_wait(monkeypatch, 0.05)
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


def test_configured_limits_apply_and_bad_values_fall_back(monkeypatch):
    monkeypatch.setattr(executor, '_limits', executor.limits())

    configured = executor.configure_limits(
        {
            'max_threads': '8',
            'queue_wait_seconds': '2.5',
            'connect_timeout_seconds': '0',
            'statement_timeout_seconds': 'lots',
            'scheduled_statement_timeout_seconds': '-5',
        }
    )

    assert configured.max_threads == 8
    assert configured.queue_wait_seconds == 2.5
    # Not positive numbers: the defaults stay.
    assert configured.connect_timeout_seconds == 30
    assert configured.statement_timeout_seconds == 30
    assert configured.scheduled_statement_timeout_seconds == 300
    # Not given at all: the default stays.
    assert configured.scheduled_max_threads == 4
    assert executor.limits() == configured


@pytest.mark.parametrize('raw', ['0.5', 'inf', '-inf', 'nan', '1e400'])
def test_values_that_would_break_the_pool_fall_back(monkeypatch, raw):
    # 0.5 threads truncates to 0, which ThreadPoolExecutor rejects; inf and nan
    # cannot become an int at all. None of them may reach the pool.
    monkeypatch.setattr(executor, '_limits', executor.limits())

    configured = executor.configure_limits({'max_threads': raw})

    assert configured.max_threads == 16


def test_fractional_wait_is_kept(monkeypatch):
    monkeypatch.setattr(executor, '_limits', executor.limits())

    assert (
        executor.configure_limits({'queue_wait_seconds': '0.5'}).queue_wait_seconds
        == 0.5
    )


def test_statement_limit_follows_the_configured_value(monkeypatch):
    monkeypatch.setattr(
        executor,
        '_limits',
        dataclasses.replace(executor.limits(), statement_timeout_seconds=45),
    )

    assert executor.current_statement_timeout() == 45


async def _until(condition, timeout=5):
    for _ in range(int(timeout / 0.01)):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError('condition not met in time')


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', ['request', 'scheduled'])
async def test_batch_starts_other_calls_while_the_first_is_still_running(lane):
    first_may_finish = threading.Event()
    second_started = threading.Event()

    def first():
        first_may_finish.wait(5)
        return 'first'

    def second():
        second_started.set()
        return 'second'

    context = contextvars.copy_context()
    if lane == 'scheduled':
        context.run(executor.use_scheduled_limits)
    batch = asyncio.create_task(
        executor.run_blocking_batch([(first, ()), (second, ())]), context=context
    )
    try:
        # The second call must not wait for the first one to finish.
        await _until(second_started.is_set)
        assert not batch.done()
    finally:
        first_may_finish.set()

    assert await batch == ['first', 'second']
