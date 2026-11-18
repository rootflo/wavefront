"""CacheManager a* methods: async client on the bound loop, sync fallback elsewhere.

No Redis server is used: the connectivity ping is patched, and the async and
sync clients' commands are replaced per test.
"""

import asyncio
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest
from redis import ConnectionError
from redis.exceptions import OutOfMemoryError

from db_repo_module.cache import cache_manager as module
from db_repo_module.cache.cache_manager import CacheManager, CacheUnavailableError
from db_repo_module.cache.redis_settings import RedisSettings


@pytest.fixture(autouse=True)
def no_redis_ping():
    with patch.object(module.Redis, 'ping', return_value=True):
        yield


def make_manager(**settings):
    return CacheManager(
        namespace='ns',
        settings=RedisSettings(initial_backoff=0.01, max_backoff=0.01, **settings),
    )


@pytest.fixture
async def bound():
    manager = make_manager()
    manager.bind_event_loop()
    yield manager
    await manager.aclose()


async def test_bound_manager_uses_the_async_client(bound, monkeypatch):
    async_get = AsyncMock(return_value='value')
    monkeypatch.setattr(bound._async_redis, 'get', async_get)
    monkeypatch.setattr(bound.redis, 'get', _must_not_call)

    assert await bound.aget_str('key') == 'value'
    async_get.assert_awaited_once_with('ns/key')


async def test_missing_key_returns_the_default(bound, monkeypatch):
    monkeypatch.setattr(bound._async_redis, 'get', AsyncMock(return_value=None))

    assert await bound.aget_str('key', 'fallback') == 'fallback'


async def test_aadd_sets_with_expiry_and_nx(bound, monkeypatch):
    async_set = AsyncMock(return_value=True)
    monkeypatch.setattr(bound._async_redis, 'set', async_set)

    assert await bound.aadd('key', 'v', expiry=60, nx=True) is True
    async_set.assert_awaited_once_with('ns/key', 'v', ex=60, nx=True)


async def test_aremove_deletes_the_namespaced_key(bound, monkeypatch):
    async_delete = AsyncMock(return_value=1)
    monkeypatch.setattr(bound._async_redis, 'delete', async_delete)
    monkeypatch.setattr(bound.redis, 'delete', _must_not_call)

    assert await bound.aremove('key') is True
    async_delete.assert_awaited_once_with('ns/key')


async def test_aremove_failure_is_reported(bound, monkeypatch):
    monkeypatch.setattr(
        bound._async_redis, 'delete', AsyncMock(side_effect=ConnectionError('down'))
    )

    with pytest.raises(CacheUnavailableError):
        await bound.aremove('key', attempts=1)


async def test_try_helpers_work_normally(bound, monkeypatch):
    monkeypatch.setattr(bound._async_redis, 'get', AsyncMock(return_value='v'))
    monkeypatch.setattr(bound._async_redis, 'set', AsyncMock(return_value=True))
    monkeypatch.setattr(bound._async_redis, 'delete', AsyncMock(return_value=1))

    assert await bound.try_aget_str('key') == 'v'
    assert await bound.try_aadd('key', 'v', expiry=60) is True
    assert await bound.try_aremove('key') is True


async def test_try_helpers_tolerate_redis_failure(bound, monkeypatch):
    down = AsyncMock(side_effect=ConnectionError('down'))
    for method in ('get', 'set', 'delete'):
        monkeypatch.setattr(bound._async_redis, method, down)
    monkeypatch.setattr(bound, 'max_retries', 1)

    assert await bound.try_aget_str('key', 'fallback') == 'fallback'
    assert await bound.try_aadd('key', 'v') is False
    assert await bound.try_aremove('key') is False


async def test_slow_redis_times_out_without_blocking_the_loop(bound, monkeypatch):
    async def hang(_key):
        await asyncio.sleep(5)

    monkeypatch.setattr(bound._async_redis, 'get', hang)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.ensure_future(ticker())
    started = time.monotonic()
    try:
        with pytest.raises(CacheUnavailableError):
            await bound.aget_str('key', timeout=0.2)
    finally:
        task.cancel()

    assert time.monotonic() - started < 1.0
    assert ticks >= 10  # the loop kept running while Redis hung


async def test_errors_are_retried_then_reported(bound, monkeypatch):
    calls = []

    async def flaky(_key):
        calls.append(1)
        raise ConnectionError('dropped')

    monkeypatch.setattr(bound._async_redis, 'get', flaky)

    with pytest.raises(CacheUnavailableError):
        await bound.aget_str('key', attempts=3)

    assert len(calls) == 3


async def test_single_attempt(bound, monkeypatch):
    calls = []

    async def flaky(_key):
        calls.append(1)
        raise ConnectionError('dropped')

    monkeypatch.setattr(bound._async_redis, 'get', flaky)

    with pytest.raises(CacheUnavailableError):
        await bound.aget_str('key', attempts=1)

    assert len(calls) == 1


async def test_out_of_memory_is_not_retried(bound, monkeypatch):
    calls = []

    async def oom(*_args, **_kwargs):
        calls.append(1)
        raise OutOfMemoryError('OOM')

    monkeypatch.setattr(bound._async_redis, 'set', oom)

    with pytest.raises(CacheUnavailableError):
        await bound.aadd('key', 'v', attempts=3)

    assert len(calls) == 1


async def test_unbound_manager_falls_back_to_the_sync_client_off_the_loop(monkeypatch):
    manager = make_manager()
    loop_thread = threading.get_ident()
    threads = []

    def sync_get(_key):
        threads.append(threading.get_ident())
        return 'value'

    monkeypatch.setattr(manager.redis, 'get', sync_get)

    assert await manager.aget_str('key') == 'value'
    assert threads and loop_thread not in threads


def test_other_loops_fall_back_to_the_sync_client(monkeypatch):
    """Scheduled jobs run asyncio.run on their own thread: no async client there."""
    manager = make_manager()

    async def bind_on_main_loop():
        manager.bind_event_loop()

    main_loop = asyncio.new_event_loop()
    try:
        main_loop.run_until_complete(bind_on_main_loop())
        monkeypatch.setattr(manager._async_redis, 'get', _must_not_call_async)
        monkeypatch.setattr(manager.redis, 'get', lambda _key: 'from-sync')

        result = {}
        worker = threading.Thread(
            target=lambda: result.setdefault(
                'value', asyncio.run(manager.aget_str('key'))
            )
        )
        worker.start()
        worker.join(5)

        assert result['value'] == 'from-sync'
    finally:
        main_loop.run_until_complete(manager.aclose())
        main_loop.close()


async def test_sync_fallback_failures_are_reported_the_same_way(monkeypatch):
    manager = make_manager(max_retries=1)

    def down(_key):
        raise ConnectionError('down')

    monkeypatch.setattr(manager.redis, 'get', down)

    with pytest.raises(CacheUnavailableError):
        await manager.aget_str('key')


async def test_async_settings_reach_the_async_pool():
    manager = make_manager(async_pool_size=7, async_command_timeout='0.5')
    manager.bind_event_loop()
    try:
        assert manager._async_redis.connection_pool.max_connections == 7
        assert manager.async_command_timeout == 0.5
    finally:
        await manager.aclose()


async def test_aclose_unbinds(bound):
    await bound.aclose()

    assert bound._async_redis is None


def _must_not_call(*_args, **_kwargs):
    raise AssertionError('the sync client must not be used here')


async def _must_not_call_async(*_args, **_kwargs):
    raise AssertionError('the async client must not be used on another loop')
