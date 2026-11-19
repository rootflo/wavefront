"""PublicKeyCache: TTL, cache-off mode, rotation refetch limits, single-flight."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from common_module.blocking_io import shutdown_blocking_io
from common_module.security.public_key_cache import (
    PublicKeyCache,
    PublicKeyUnavailableError,
    seconds_setting,
)


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


class Fetcher:
    def __init__(self, key='k1', delay=0.0):
        self.key = key
        self.delay = delay
        self.calls = 0
        self.threads = []
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
        self.threads.append(threading.get_ident())
        time.sleep(self.delay)
        return self.key


def accept_only(expected):
    """A decode function: claims for the right key, None (bad signature) otherwise."""
    return lambda key: {'ok': True} if key == expected else None


def test_key_is_fetched_once_while_fresh():
    fetch = Fetcher()
    cache = PublicKeyCache(fetch)

    for _ in range(10):
        assert cache.verify(accept_only('k1')) == {'ok': True}

    assert fetch.calls == 1


def test_key_is_refetched_after_it_expires():
    fetch = Fetcher()
    cache = PublicKeyCache(fetch, cache_seconds=0.05)

    cache.verify(accept_only('k1'))
    time.sleep(0.1)
    cache.verify(accept_only('k1'))

    assert fetch.calls == 2


def test_zero_disables_the_cache_and_skips_rotation_refetch():
    fetch = Fetcher()
    cache = PublicKeyCache(fetch, cache_seconds=0)

    assert cache.cached() is None
    cache.verify(accept_only('k1'))
    cache.verify(accept_only('k1'))
    assert cache.verify(accept_only('other')) is None

    assert fetch.calls == 3  # one per verification, no extra refetch


def test_rotation_is_picked_up_once_allowed():
    fetch = Fetcher('old')
    cache = PublicKeyCache(fetch, refresh_min_seconds=0)
    cache.verify(accept_only('old'))
    fetch.key = 'new'

    assert cache.verify(accept_only('new')) == {'ok': True}
    assert fetch.calls == 2


def test_rotation_refetch_is_rate_limited():
    fetch = Fetcher()
    cache = PublicKeyCache(fetch, refresh_min_seconds=60)
    cache.verify(accept_only('k1'))
    cache._fetched_at -= 120  # old enough for exactly one refetch

    results = [cache.verify(accept_only('forged-key')) for _ in range(50)]

    assert results == [None] * 50
    assert fetch.calls == 2


def test_concurrent_misses_fetch_once():
    fetch = Fetcher(delay=0.1)
    cache = PublicKeyCache(fetch)
    start_together = threading.Barrier(8)

    def reader():
        start_together.wait(5)  # all eight callers miss at the same moment
        return cache.get()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = [f.result(10) for f in [executor.submit(reader) for _ in range(8)]]

    assert results == ['k1'] * 8
    assert fetch.calls == 1


async def test_async_verify_fetches_off_the_loop_and_then_serves_from_cache():
    fetch = Fetcher()
    cache = PublicKeyCache(fetch)

    assert await cache.averify(accept_only('k1')) == {'ok': True}
    assert await cache.averify(accept_only('k1')) == {'ok': True}

    assert fetch.calls == 1
    assert threading.get_ident() not in fetch.threads


async def test_async_rotation_refetch_runs_off_the_loop():
    fetch = Fetcher('old')
    cache = PublicKeyCache(fetch, refresh_min_seconds=0)
    await cache.averify(accept_only('old'))
    fetch.key = 'new'

    assert await cache.averify(accept_only('new')) == {'ok': True}
    assert threading.get_ident() not in fetch.threads


def test_fetch_errors_propagate():
    def broken():
        raise RuntimeError('KMS down')

    cache = PublicKeyCache(broken)

    with pytest.raises(PublicKeyUnavailableError, match='KMS down'):
        cache.verify(accept_only('k1'))


async def test_fetch_errors_are_never_jwt_errors():
    """A KMS outage must not be mistaken for an invalid token (401)."""
    import jwt

    def broken():
        raise jwt.InvalidTokenError('looks like a token problem')

    cache = PublicKeyCache(broken)

    with pytest.raises(PublicKeyUnavailableError) as raised:
        await cache.averify(accept_only('k1'))
    assert not isinstance(raised.value, jwt.InvalidTokenError)


def test_seconds_setting():
    assert seconds_setting(None, 600) == 600
    assert seconds_setting('', 60) == 60
    assert seconds_setting('0', 600) == 0
    assert seconds_setting('2.5', 600) == 2.5
    with pytest.raises(ValueError):
        seconds_setting('-1', 600)


@pytest.mark.parametrize('bad', ['inf', 'nan', '-1'])
def test_seconds_setting_rejects_non_finite_and_negative(bad):
    with pytest.raises(ValueError):
        seconds_setting(bad, 60)
