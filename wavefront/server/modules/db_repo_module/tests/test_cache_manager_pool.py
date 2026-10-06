"""Redis connection pool sizing and blocking behaviour for CacheManager. No
Redis server is used: the connectivity ping and socket connects are patched."""

import importlib.util
import threading
import time
from unittest.mock import patch

import pytest
from redis import BlockingConnectionPool, Connection, ConnectionError, RedisError

from db_repo_module.cache import cache_manager as module
from db_repo_module.cache.cache_manager import CacheManager


@pytest.fixture(autouse=True)
def no_redis_ping():
    with patch.object(module.Redis, 'ping', return_value=True):
        yield


def import_fresh(monkeypatch, *unset_env):
    """A separate copy of cache_manager imported with `unset_env` removed, so
    its import-time defaults are checked without reloading the shared module."""
    for name in unset_env:
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location(
        'cache_manager_fresh', module.__file__
    )
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    return fresh


def test_default_pool_size_is_20(monkeypatch):
    fresh = import_fresh(monkeypatch, 'REDIS_POOL_SIZE')

    assert fresh.DEFAULT_POOL_SIZE == 20
    with patch.object(fresh.Redis, 'ping', return_value=True):
        assert fresh.CacheManager(namespace='test').pool.max_connections == 20


def test_pool_size_is_read_from_env_at_import(monkeypatch):
    monkeypatch.setenv('REDIS_POOL_SIZE', '15')

    assert import_fresh(monkeypatch).DEFAULT_POOL_SIZE == 15


def test_default_comes_from_module_setting(monkeypatch):
    monkeypatch.setattr(module, 'DEFAULT_POOL_SIZE', 35)

    assert CacheManager(namespace='test').pool.max_connections == 35


def test_explicit_pool_size_wins(monkeypatch):
    monkeypatch.setattr(module, 'DEFAULT_POOL_SIZE', 35)

    assert CacheManager(namespace='test', pool_size=7).pool.max_connections == 7


# --- blocking pool -----------------------------------------------------------


@pytest.fixture
def offline_connections():
    """Let the pool hand out connections without a Redis server."""
    with (
        patch.object(Connection, 'connect'),
        patch.object(Connection, 'can_read', return_value=False),
    ):
        yield


def make_manager(monkeypatch, pool_size=1, timeout=0.2):
    monkeypatch.setattr(module, 'DEFAULT_POOL_TIMEOUT', timeout)
    return CacheManager(namespace='test', pool_size=pool_size)


def test_pool_blocks_with_the_configured_timeout(monkeypatch):
    manager = make_manager(monkeypatch, timeout=1.5)

    assert isinstance(manager.pool, BlockingConnectionPool)
    assert manager.pool.timeout == 1.5


def test_default_wait_is_two_seconds(monkeypatch):
    fresh = import_fresh(monkeypatch, 'REDIS_POOL_TIMEOUT')

    assert fresh.DEFAULT_POOL_TIMEOUT == 2


def test_exhausted_pool_waits_then_raises(monkeypatch, offline_connections):
    pool = make_manager(monkeypatch, pool_size=1, timeout=0.2).pool
    held = pool.get_connection()

    started = time.monotonic()
    with pytest.raises(ConnectionError, match='No connection available'):
        pool.get_connection()
    waited = time.monotonic() - started

    assert 0.15 <= waited < 1.0
    pool.release(held)


def test_waiter_gets_the_connection_once_it_is_released(
    monkeypatch, offline_connections
):
    pool = make_manager(monkeypatch, pool_size=1, timeout=2).pool
    held = pool.get_connection()
    threading.Timer(0.1, pool.release, args=(held,)).start()

    started = time.monotonic()
    connection = pool.get_connection()

    assert connection is held
    assert time.monotonic() - started < 1.0
    pool.release(connection)


def test_retry_with_backoff_retries_redis_errors(monkeypatch):
    # The except clause used to list ConnectionPool (not an exception), which
    # turned every caught error into a TypeError instead of a retry.
    manager = make_manager(monkeypatch)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RedisError('transient')
        return 'ok'

    assert manager._retry_with_backoff(flaky) == 'ok'
    assert len(calls) == 3
