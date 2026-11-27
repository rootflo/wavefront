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

from db_repo_module.cache import base_cache as module
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


# --- timeouts and retries from [redis] settings ---------------------------------


def test_timeouts_reach_the_connection_pool():
    manager = CacheManager(
        namespace='test',
        settings=RedisSettings(socket_timeout=5, connection_timeout=3),
    )
    kwargs = manager.pool.connection_kwargs

    assert kwargs['socket_timeout'] == 5.0
    assert kwargs['socket_connect_timeout'] == 3.0


def test_string_values_from_config_ini_parse():
    manager = CacheManager(
        namespace='test',
        settings=RedisSettings(
            socket_timeout='5',
            connection_timeout='3',
            max_retries='2',
            initial_backoff='0.1',
            max_backoff='0.5',
        ),
    )

    assert manager.pool.connection_kwargs['socket_timeout'] == 5.0
    assert manager.max_retries == 2
    assert manager.initial_backoff == 0.1
    assert manager.max_backoff == 0.5


def test_missing_config_keys_fall_back_to_defaults():
    """An ini without the new keys passes None; that must not break startup."""
    settings = RedisSettings(
        socket_timeout=None,
        connection_timeout=None,
        max_retries=None,
        initial_backoff=None,
        max_backoff=None,
    )

    assert settings.socket_timeout == 60
    assert settings.connection_timeout == 60
    assert settings.max_retries == 3
    assert settings.initial_backoff == 1
    assert settings.max_backoff == 10


def _failing_set(manager, monkeypatch):
    calls = []

    def flaky(*_args, **_kwargs):
        calls.append(1)
        raise ConnectionError('transient')

    monkeypatch.setattr(manager.redis, 'set', flaky)
    return calls


def test_retries_follow_the_configured_attempts_and_backoff(monkeypatch):
    manager = CacheManager(
        namespace='test',
        settings=RedisSettings(max_retries=3, initial_backoff=0.1, max_backoff=0.15),
    )
    waits = []
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    calls = _failing_set(manager, monkeypatch)

    with pytest.raises(RetryError):
        manager.add('key', 'value')

    assert len(calls) == 3
    # 0.1 s, then doubled to 0.2 s but capped at max_backoff.
    assert waits == pytest.approx([0.1, 0.15])


def test_default_retry_policy_is_unchanged(monkeypatch):
    """Without settings: 3 attempts, waiting 1 s then 2 s, as before."""
    manager = CacheManager(namespace='test')
    waits = []
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    calls = _failing_set(manager, monkeypatch)

    with pytest.raises(RetryError):
        manager.add('key', 'value')

    assert len(calls) == 3
    assert waits == pytest.approx([1, 2])


def test_single_attempt_does_not_wait(monkeypatch):
    manager = CacheManager(namespace='test', settings=RedisSettings(max_retries=1))
    waits = []
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    calls = _failing_set(manager, monkeypatch)

    with pytest.raises(RetryError):
        manager.add('key', 'value')

    assert len(calls) == 1
    assert waits == []


# --- pubsub connection -----------------------------------------------------------


def test_subscribe_uses_a_separate_pool_without_read_timeout():
    manager = CacheManager(namespace='test', settings=RedisSettings(socket_timeout=5))

    pubsub = manager.subscribe()

    assert pubsub.connection_pool is not manager.pool
    assert pubsub.connection_pool.connection_kwargs['socket_timeout'] is None
    assert pubsub.connection_pool.connection_kwargs['socket_keepalive'] is True
    # Keeps redis-py's built-in retry so a dropped listener reconnects and resubscribes.
    assert pubsub.connection_pool.connection_kwargs['retry_on_timeout'] is True
    # The main pool keeps its short timeout.
    assert manager.pool.connection_kwargs['socket_timeout'] == 5.0


@pytest.mark.parametrize(
    'settings, connection_class',
    [
        (RedisSettings(socket_timeout=5), module._PubSubConnection),
        (
            RedisSettings(socket_timeout=5, protocol='rediss'),
            module._PubSubSSLConnection,
        ),
    ],
    ids=['plain', 'ssl'],
)
def test_pubsub_pool_bounds_the_handshake(settings, connection_class):
    manager = CacheManager(namespace='test', settings=settings)

    pool = manager.subscribe().connection_pool

    assert pool.connection_class is connection_class
    assert pool.connection_kwargs['handshake_timeout'] == 5.0


class _RecordingSocket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)


def test_pubsub_handshake_runs_under_its_own_timeout_then_waits_indefinitely():
    conn = module._PubSubConnection(handshake_timeout=2.0, socket_timeout=None)
    sock = conn._sock = _RecordingSocket()
    seen = []

    with patch.object(
        Connection, 'on_connect', lambda self: seen.append(list(sock.timeouts))
    ):
        conn.on_connect()

    # AUTH/SELECT were read under the handshake timeout ...
    assert seen == [[2.0]]
    # ... and the socket is back to no read timeout for idle pubsub waits.
    assert sock.timeouts == [2.0, None]


def test_pubsub_handshake_timeout_surfaces_and_leaves_no_socket():
    conn = module._PubSubConnection(handshake_timeout=2.0, socket_timeout=None)
    conn._sock = _RecordingSocket()

    def unanswered_handshake(self):
        self._sock = None  # redis-py disconnects on a failed read
        raise RedisTimeoutError('Timeout reading from socket')

    with patch.object(Connection, 'on_connect', unanswered_handshake):
        with pytest.raises(RedisTimeoutError):
            conn.on_connect()

    assert conn._sock is None


def test_pubsub_pool_is_created_once():
    manager = CacheManager(namespace='test')

    first = manager.subscribe().connection_pool
    second = manager.subscribe().connection_pool

    assert first is second


def test_pubsub_pool_is_not_created_until_subscribe():
    assert CacheManager(namespace='test')._pubsub_pool is None


def test_close_disconnects_the_pubsub_pool_too():
    manager = CacheManager(namespace='test')
    pubsub_pool = manager.subscribe().connection_pool

    with (
        patch.object(manager.pool, 'disconnect') as main_disconnect,
        patch.object(pubsub_pool, 'disconnect') as pubsub_disconnect,
    ):
        manager.close()

    main_disconnect.assert_called_once()
    pubsub_disconnect.assert_called_once()


def test_redis_py_does_not_retry_timeouts_on_its_own():
    """Only _retry_policy retries; a hidden redis-py retry would double each wait."""
    manager = CacheManager(namespace='test')

    assert manager.pool.connection_kwargs['retry_on_timeout'] is False


def test_exhausted_retries_log_one_error(monkeypatch, caplog):
    """Each attempt is a warning; one error when the call fails for good, so a
    Redis outage is one error event per call, not one per attempt."""
    import logging

    manager = make_manager()
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)

    def down(*_args, **_kwargs):
        raise ConnectionError('down')

    monkeypatch.setattr(manager.redis, 'set', down)

    with caplog.at_level(logging.DEBUG), pytest.raises(RetryError):
        manager.add('key', 'value')

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    attempts = [r for r in caplog.records if 'Error adding key' in r.getMessage()]
    assert len(errors) == 1
    assert 'add failed after retries' in errors[0].getMessage()
    assert len(attempts) == 3
    assert all(r.levelno == logging.WARNING for r in attempts)
