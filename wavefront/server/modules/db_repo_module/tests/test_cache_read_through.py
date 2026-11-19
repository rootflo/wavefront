"""read_through / invalidating: generation-checked cache-aside.

Unit tests use a small in-memory fake that runs the same logic as the two Lua
scripts. ``test_lua_scripts_against_real_redis`` runs the real scripts when
REDIS_URL is set (locally or in CI), so their syntax and semantics are checked.
"""

import asyncio
import os
from unittest.mock import patch

import pytest

from db_repo_module.cache import cache_manager as module
from db_repo_module.cache.cache_manager import CacheManager, CacheUnavailableError
from db_repo_module.cache.redis_settings import RedisSettings


class FakeRedis:
    """Enough of redis.asyncio for the read-through scripts and rotation."""

    def __init__(self):
        self.store = {}
        self.down = False

    def _check(self):
        if self.down:
            raise module.ConnectionError('redis down')

    async def eval(self, script, numkeys, *args):
        self._check()
        keys, argv = args[:numkeys], [str(a) for a in args[numkeys:]]
        if script == CacheManager._RT_READ:
            token = self.store.get(keys[1])
            if token is None:
                token = argv[0]
                self.store[keys[1]] = token
            return [token, self.store.get(keys[0])]
        if script == CacheManager._RT_FILL:
            if self.store.get(keys[1]) != argv[0]:
                return 0
            self.store[keys[0]] = f'{argv[0]}\n{argv[1]}'
            return 1
        raise AssertionError('unknown script')

    def pipeline(self, transaction=True):
        fake = self
        ops = []

        class Pipe:
            def set(self, key, value, ex=None):
                ops.append(('set', key, value))

            def delete(self, key):
                ops.append(('del', key))

            async def execute(self):
                fake._check()
                for op in ops:
                    if op[0] == 'set':
                        fake.store[op[1]] = op[2]
                    else:
                        fake.store.pop(op[1], None)
                return [True] * len(ops)

        return Pipe()

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def no_redis_ping():
    with patch.object(module.Redis, 'ping', return_value=True):
        yield


@pytest.fixture
async def cache():
    manager = CacheManager(
        namespace='ns',
        settings=RedisSettings(initial_backoff=0.01, max_backoff=0.01, max_retries=1),
    )
    manager._async_redis = FakeRedis()
    manager._async_loop = asyncio.get_running_loop()
    yield manager


class Loader:
    def __init__(self, value='v1'):
        self.value = value
        self.calls = 0
        self.gate = None  # an asyncio.Event to pause the load mid-flight

    async def __call__(self):
        self.calls += 1
        value = self.value  # read the "source" first, like a DB query
        if self.gate is not None:
            await self.gate.wait()
        return value


async def loaded(loader, timeout=2.0):
    """Wait until the reader is inside its loader (token captured, source read)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while loader.calls == 0:
        assert asyncio.get_running_loop().time() < deadline, 'reader never loaded'
        await asyncio.sleep(0.001)


async def test_miss_then_hit(cache):
    loader = Loader()

    assert await cache.read_through('k', loader, ttl=60) == 'v1'
    assert await cache.read_through('k', loader, ttl=60) == 'v1'

    assert loader.calls == 1


async def test_not_found_is_not_cached(cache):
    loader = Loader(value=None)

    assert await cache.read_through('k', loader, ttl=60) is None
    assert await cache.read_through('k', loader, ttl=60) is None

    assert loader.calls == 2


async def test_invalidation_makes_the_next_read_load_again(cache):
    loader = Loader()
    await cache.read_through('k', loader, ttl=60)

    loader.value = 'v2'
    async with cache.invalidating('k'):
        pass

    assert await cache.read_through('k', loader, ttl=60) == 'v2'


async def test_a_late_fill_cannot_restore_the_old_value(cache):
    """The CodeRabbit race: read old, writer commits and invalidates, late fill."""
    loader = Loader('old')
    loader.gate = asyncio.Event()
    reader = asyncio.ensure_future(cache.read_through('k', loader, ttl=60))
    await loaded(loader)  # the reader has captured the token and read 'old'

    async with cache.invalidating('k'):
        loader.value = 'new'  # the write to the source of truth
    loader.gate.set()
    assert await reader == 'old'  # that request already had the old value

    loader.gate = None
    assert await cache.read_through('k', loader, ttl=60) == 'new'


async def test_a_reader_racing_the_change_is_defeated_by_the_second_rotation(cache):
    """Reader captures the token after the first rotation but reads the source
    before the commit; the rotation after the body makes its fill invalid."""
    loader = Loader('old')
    loader.gate = asyncio.Event()
    reader = None

    async with cache.invalidating('k'):
        reader = asyncio.ensure_future(cache.read_through('k', loader, ttl=60))
        await loaded(loader)
        loader.value = 'new'
    loader.gate.set()
    await reader

    loader.gate = None
    assert await cache.read_through('k', loader, ttl=60) == 'new'


async def test_missing_token_never_validates_a_value(cache):
    loader = Loader()
    await cache.read_through('k', loader, ttl=60)
    value_key, gen_key = cache._rt_keys('k')
    del cache._async_redis.store[gen_key]  # evicted or expired

    loader.value = 'v2'
    assert await cache.read_through('k', loader, ttl=60) == 'v2'


async def test_redis_down_on_read_falls_back_to_the_loader(cache):
    cache._async_redis.down = True
    loader = Loader()

    assert await cache.read_through('k', loader, ttl=60) == 'v1'
    assert await cache.read_through('k', loader, ttl=60) == 'v1'
    assert loader.calls == 2


async def test_redis_down_before_a_change_stops_it(cache):
    cache._async_redis.down = True
    changed = False

    with pytest.raises(CacheUnavailableError):
        async with cache.invalidating('k'):
            changed = True

    assert changed is False


async def test_redis_down_after_a_change_is_tolerated(cache):
    async with cache.invalidating('k'):
        cache._async_redis.down = True  # fails between the two rotations

    # no exception: the change happened; the failure is logged


async def test_body_error_still_rotates_and_propagates(cache):
    loader = Loader()
    await cache.read_through('k', loader, ttl=60)

    with pytest.raises(RuntimeError):
        async with cache.invalidating('k'):
            raise RuntimeError('db write failed')

    loader.value = 'v2'
    assert await cache.read_through('k', loader, ttl=60) == 'v2'


async def test_keys_share_a_hash_slot_and_a_separate_prefix(cache):
    value_key, gen_key = cache._rt_keys('agent:1')

    assert value_key == 'ns/rt/{agent:1}'
    assert gen_key == 'ns/rt/{agent:1}:gen'


@pytest.mark.skipif(not os.environ.get('REDIS_URL'), reason='needs REDIS_URL')
async def test_lua_scripts_against_real_redis():
    from redis import asyncio as aioredis

    client = aioredis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    value_key, gen_key = 'test/rt/{lua-check}', 'test/rt/{lua-check}:gen'
    try:
        await client.delete(value_key, gen_key)
        token, value = await client.eval(
            CacheManager._RT_READ, 2, value_key, gen_key, 'tok-1', 60
        )
        assert (token, value) == ('tok-1', None)

        assert (
            await client.eval(
                CacheManager._RT_FILL,
                2,
                value_key,
                gen_key,
                'tok-1',
                'payload\nline',
                60,
            )
            == 1
        )
        token, value = await client.eval(
            CacheManager._RT_READ, 2, value_key, gen_key, 'unused', 60
        )
        assert token == 'tok-1'
        assert value == 'tok-1\npayload\nline'

        await client.set(gen_key, 'tok-2')  # a writer rotated
        assert (
            await client.eval(
                CacheManager._RT_FILL, 2, value_key, gen_key, 'tok-1', 'stale', 60
            )
            == 0
        )
    finally:
        await client.delete(value_key, gen_key)
        await client.aclose()
