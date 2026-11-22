"""Redis connection pool sizing and blocking behaviour for CacheManager. No
Redis server is used: the connectivity ping and socket connects are patched."""

import threading
import time
from unittest.mock import patch

import pytest
from redis import BlockingConnectionPool, Connection, ConnectionError, RedisError
from redis.exceptions import OutOfMemoryError
from redis.exceptions import TimeoutError as RedisTimeoutError
from tenacity import RetryError

from db_repo_module.cache import cache_manager as module
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.redis_settings import RedisSettings


@pytest.fixture(autouse=True)
def no_redis_ping():
    with patch.object(module.Redis, 'ping', return_value=True):
        yield


def test_default_pool_size_is_20():
    assert CacheManager(namespace='test').pool.max_connections == 20


def test_explicit_pool_size_wins():
    assert (
        CacheManager(
            namespace='test', settings=RedisSettings(pool_size=7)
        ).pool.max_connections
        == 7
    )


# --- blocking pool -----------------------------------------------------------


@pytest.fixture
def offline_connections():
    """Let the pool hand out connections without a Redis server."""
    with (
        patch.object(Connection, 'connect'),
        patch.object(Connection, 'can_read', return_value=False),
    ):
        yield


def make_manager(pool_size=1, timeout=0.2):
    return CacheManager(
        namespace='test',
        settings=RedisSettings(pool_size=pool_size, pool_timeout=timeout),
    )


def test_pool_blocks_with_the_configured_timeout():
    manager = make_manager(timeout=1.5)

    assert isinstance(manager.pool, BlockingConnectionPool)
    assert manager.pool.timeout == 1.5


def test_default_wait_is_two_seconds():
    assert CacheManager(namespace='test').pool.timeout == 2.0


def test_exhausted_pool_waits_then_raises(offline_connections):
    pool = make_manager(pool_size=1, timeout=0.2).pool
    held = pool.get_connection()

    started = time.monotonic()
    with pytest.raises(ConnectionError, match='No connection available'):
        pool.get_connection()
    waited = time.monotonic() - started

    assert 0.15 <= waited < 1.0
    pool.release(held)


def test_waiter_gets_the_connection_once_it_is_released(offline_connections):
    pool = make_manager(pool_size=1, timeout=2).pool
    held = pool.get_connection()
    threading.Timer(0.1, pool.release, args=(held,)).start()

    started = time.monotonic()
    connection = pool.get_connection()

    assert connection is held
    assert time.monotonic() - started < 1.0
    pool.release(connection)


def test_empty_password_becomes_none():
    assert RedisSettings(password='').password is None


def test_out_of_memory_is_not_retried(monkeypatch):
    """OOM fails the same way every time; retrying only blocks the event loop."""
    manager = make_manager()
    calls = []

    def oom(*_args, **_kwargs):
        calls.append(1)
        raise OutOfMemoryError('OOM command not allowed when used memory > maxmemory')

    monkeypatch.setattr(manager.redis, 'set', oom)

    with pytest.raises(OutOfMemoryError):
        manager.add('key', 'value')

    assert len(calls) == 1


def test_connection_errors_are_still_retried(monkeypatch):
    """An exhausted retry raises RetryError, unlike the OOM path above."""
    manager = make_manager()
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    calls = []

    def flaky(*_args, **_kwargs):
        calls.append(1)
        raise ConnectionError('transient')

    monkeypatch.setattr(manager.redis, 'set', flaky)

    with pytest.raises(RetryError):
        manager.add('key', 'value')

    assert len(calls) == 3


def test_oom_predicate_discriminates():
    # redis's TimeoutError, not the builtin.
    assert module._is_retryable_redis_error(ConnectionError('dropped')) is True
    assert module._is_retryable_redis_error(RedisTimeoutError('slow')) is True
    assert module._is_retryable_redis_error(RedisError('other')) is True
    assert module._is_retryable_redis_error(OutOfMemoryError('OOM')) is False


def test_invalidate_query_scans_instead_of_using_keys(monkeypatch):
    manager = make_manager()
    scanned = {}
    deleted = []

    def fake_scan_iter(match=None, count=None):
        scanned['match'] = match
        scanned['count'] = count
        return iter(f'test/agent_{i}' for i in range(1203))

    monkeypatch.setattr(manager.redis, 'scan_iter', fake_scan_iter)
    monkeypatch.setattr(manager.redis, 'keys', _forbidden_keys)
    monkeypatch.setattr(
        manager.redis, 'delete', lambda *keys: deleted.append(keys) or len(keys)
    )

    assert manager.invalidate_query('agent_*') == 1203
    assert scanned['match'] == 'test/agent_*'
    assert [len(batch) for batch in deleted] == [500, 500, 203]


def _forbidden_keys(*_args, **_kwargs):
    raise AssertionError('invalidate_query must not call KEYS')


def test_invalidate_query_with_no_matches(monkeypatch):
    manager = make_manager()
    monkeypatch.setattr(manager.redis, 'scan_iter', lambda **_kwargs: iter([]))
    monkeypatch.setattr(manager.redis, 'keys', _forbidden_keys)

    assert manager.invalidate_query('nothing_*') == 0


def test_retry_with_backoff_retries_redis_errors(monkeypatch):
    # The except clause used to list ConnectionPool (not an exception), which
    # turned every caught error into a TypeError instead of a retry.
    manager = make_manager()
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RedisError('transient')
        return 'ok'

    assert manager._retry_with_backoff(flaky) == 'ok'
    assert len(calls) == 3
