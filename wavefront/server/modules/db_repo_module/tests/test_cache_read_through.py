"""read_through / invalidating: generation-checked cache-aside.

Unit tests use a small in-memory fake that runs the same logic as the two Lua
scripts. ``test_lua_scripts_against_real_redis`` runs the real scripts when
REDIS_URL is set (locally or in CI), so their syntax and semantics are checked.
"""

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest

from db_repo_module.cache import base_cache as module
from db_repo_module.cache import lua_scripts
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
        return self._run_script(script, keys, argv)

    def _run_script(self, script, keys, argv):
        store = self.store
        if script == lua_scripts.READ_SCRIPT:
            token = store.get(keys[1])
            if token is None:
                if store.get(keys[2]):
                    return ['pending:lost', None]
                token = argv[0]
                store[keys[1]] = token
            return [token, store.get(keys[0])]
        if script == lua_scripts.FILL_SCRIPT:
            if argv[0].startswith('pending:') or store.get(keys[1]) != argv[0]:
                return 0
            store[keys[0]] = f'{argv[0]}\n{argv[1]}'
            return 1
        if script == lua_scripts.BEGIN_CHANGE_SCRIPT:
            store.setdefault(keys[2], set()).add(argv[2])
            store[keys[1]] = argv[0]
            store.pop(keys[0], None)
            return 1
        if script == lua_scripts.END_CHANGE_SCRIPT:
            writers = store.get(keys[2], set())
            writers.discard(argv[2])
            store.pop(keys[0], None)
            if writers:
                return 0
            store.pop(keys[2], None)
            store[keys[1]] = argv[0]
            return 1
        raise AssertionError('unknown script')

    def pipeline(self, transaction=True):
        fake = self
        fake.pipelines = getattr(fake, 'pipelines', 0) + 1
        ops = []

        class Pipe:
            def eval(self, script, numkeys, *args):
                keys, argv = args[:numkeys], [str(a) for a in args[numkeys:]]
                ops.append(('eval', script, keys, argv))

            def delete(self, key):
                ops.append(('del', key))

            def _apply(self):
                fake._check()
                results = []
                for op in ops:
                    if op[0] == 'eval':
                        results.append(fake._run_script(*op[1:]))
                    else:
                        results.append(fake.store.pop(op[1], None) is not None)
                return results

            async def execute(self):
                return self._apply()

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
    assert await reader == 'old'  # it read the source before the commit

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

    async def failing_change():
        async with cache.invalidating('k'):
            raise RuntimeError('db write failed')

    with pytest.raises(RuntimeError):
        await failing_change()

    loader.value = 'v2'
    assert await cache.read_through('k', loader, ttl=60) == 'v2'


async def test_keys_share_a_hash_slot_and_a_separate_prefix(cache):
    value_key, gen_key = cache._rt_keys('agent:1')

    assert value_key == 'ns/rt/{agent:1}'
    assert gen_key == 'ns/rt/{agent:1}:gen'


async def test_reads_bypass_the_cache_while_a_change_is_pending(cache):
    loader = Loader('v1')
    await cache.read_through('k', loader, ttl=60)  # cached

    async with cache.invalidating('k'):
        loader.value = 'in-flight'
        assert await cache.read_through('k', loader, ttl=60) == 'in-flight'
        assert await cache.read_through('k', loader, ttl=60) == 'in-flight'
        value_key, _ = cache._rt_keys('k')
        assert value_key not in cache._async_redis.store  # nothing was filled

    assert loader.calls == 3


async def test_failed_final_rotation_leaves_the_key_uncacheable_not_stale(cache):
    """A read inside the change window must never become valid, even if the
    rotation after the change fails."""
    loader = Loader('old')
    real_rotate = cache._rotate

    async def failing_after(keys, *, pending, writer):
        if not pending:
            raise CacheUnavailableError('down after the change')
        await real_rotate(keys, pending=pending, writer=writer)

    cache._rotate = failing_after
    async with cache.invalidating('k'):
        await cache.read_through('k', loader, ttl=60)  # reads 'old' mid-change
        loader.value = 'new'  # the commit
    cache._rotate = real_rotate

    assert await cache.read_through('k', loader, ttl=60) == 'new'
    value_key, gen_key = cache._rt_keys('k')
    assert cache._async_redis.store[gen_key].startswith('pending:')
    assert value_key not in cache._async_redis.store
    # The marker and the writer count expire (simulated): caching resumes.
    del cache._async_redis.store[gen_key]
    del cache._async_redis.store[cache._rt_writers_key('k')]
    assert await cache.read_through('k', loader, ttl=60) == 'new'
    assert await cache.read_through('k', loader, ttl=60) == 'new'
    assert loader.calls == 3


async def test_many_keys_are_rotated_in_one_round_trip(cache):
    keys = [f'v{i}' for i in range(50)]
    cache._async_redis.pipelines = 0

    async with cache.invalidating(*keys):
        pass

    assert cache._async_redis.pipelines == 2  # one before, one after


async def test_a_key_stays_pending_until_the_last_writer_finishes(cache):
    loader = Loader('v1')
    first = cache.invalidating('k')
    second = cache.invalidating('k')
    await first.__aenter__()
    await second.__aenter__()

    await first.__aexit__(None, None, None)  # the second writer is still active
    loader.value = 'mid-change'
    assert await cache.read_through('k', loader, ttl=60) == 'mid-change'
    value_key, _ = cache._rt_keys('k')
    assert value_key not in cache._async_redis.store  # still not cacheable

    await second.__aexit__(None, None, None)
    loader.value = 'v2'
    assert await cache.read_through('k', loader, ttl=60) == 'v2'
    assert await cache.read_through('k', loader, ttl=60) == 'v2'
    assert loader.calls == 2  # the last read was a hit


async def test_a_retried_end_cannot_end_another_writers_change(cache):
    """A retry can re-run a writer's end after the first attempt landed. That
    must neither remove the other writer nor restore an older token."""
    await cache._rotate(('k',), pending=True, writer='a')
    await cache._rotate(('k',), pending=True, writer='b')
    await cache._rotate(('k',), pending=False, writer='a')
    await cache._rotate(('k',), pending=False, writer='a')  # the retry

    _, gen_key = cache._rt_keys('k')
    assert cache._async_redis.store[gen_key].startswith('pending:')
    loader = Loader('mid-change')
    await cache.read_through('k', loader, ttl=60)
    value_key, _ = cache._rt_keys('k')
    assert value_key not in cache._async_redis.store


async def test_an_evicted_marker_still_bypasses_while_a_writer_is_active(cache):
    loader = Loader('old')
    async with cache.invalidating('k'):
        _, gen_key = cache._rt_keys('k')
        del cache._async_redis.store[gen_key]  # evicted mid-change
        await cache.read_through('k', loader, ttl=60)
        value_key, _ = cache._rt_keys('k')
        assert value_key not in cache._async_redis.store
        assert gen_key not in cache._async_redis.store  # no fresh token created


async def test_a_loader_error_is_raised_once_not_retried(cache):
    calls = 0

    async def failing_loader():
        nonlocal calls
        calls += 1
        raise CacheUnavailableError("the loader's own dependency is down")

    async with cache.invalidating('k'):  # pending: the read bypasses the cache
        with pytest.raises(CacheUnavailableError):
            await cache.read_through('k', failing_loader, ttl=60)

    assert calls == 1


async def test_sync_fallback_rotation_retries():
    """Before the async client is bound (or from another loop) rotation runs on
    the sync client; it gets the same retry budget as the async path."""
    manager = CacheManager(
        namespace='ns',
        settings=RedisSettings(initial_backoff=0.01, max_backoff=0.01, max_retries=3),
    )
    attempts = 0

    class FlakyPipe:
        def eval(self, *args):
            pass

        def delete(self, key):
            pass

        def execute(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise module.ConnectionError('blip')
            return []

    class SyncRedis:
        def pipeline(self, transaction=True):
            return FlakyPipe()

    manager.redis = SyncRedis()  # no async client bound: the sync path runs

    await manager._rotate(('k',), pending=True, writer='w1')

    assert attempts == 2


@pytest.mark.skipif(not os.environ.get('REDIS_URL'), reason='needs REDIS_URL')
async def test_lua_scripts_against_real_redis():
    from redis import asyncio as aioredis

    client = aioredis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    base = f'test/rt/{{lua-check-{uuid.uuid4().hex}}}'  # unique per run
    value_key, gen_key, writers_key = base, f'{base}:gen', f'{base}:w'
    keys = (value_key, gen_key, writers_key)

    async def read(new_token):
        return await client.eval(lua_scripts.READ_SCRIPT, 3, *keys, new_token, 60)

    async def fill(token, value):
        return await client.eval(
            lua_scripts.FILL_SCRIPT, 2, value_key, gen_key, token, value, 60
        )

    try:
        assert await read('tok-1') == ['tok-1', None]
        assert await fill('tok-1', 'payload\nline') == 1
        assert await read('unused') == ['tok-1', 'tok-1\npayload\nline']

        await client.set(gen_key, 'tok-2')  # a writer rotated
        assert await fill('tok-1', 'stale') == 0

        # Two overlapping writers: the key stays pending until the last leaves.
        async def begin(writer):
            return await client.eval(
                lua_scripts.BEGIN_CHANGE_SCRIPT,
                3,
                *keys,
                f'pending:{writer}',
                60,
                writer,
            )

        async def end(writer, token):
            return await client.eval(
                lua_scripts.END_CHANGE_SCRIPT, 3, *keys, token, 60, writer
            )

        assert await begin('a') and await begin('b')
        assert await client.get(value_key) is None
        assert await fill('pending:b', 'x') == 0
        assert await end('a', 'tok-3') == 0
        assert await end('a', 'tok-3b') == 0  # a retried end changes nothing
        assert (await read('unused'))[0] == 'pending:b'
        await client.delete(gen_key)  # the marker is evicted mid-change
        assert (await read('unused'))[0].startswith('pending:')
        assert await client.get(gen_key) is None  # no fresh token was created
        assert await end('b', 'tok-4') == 1
        assert await read('unused') == ['tok-4', None]
        assert await client.exists(writers_key) == 0
    finally:
        await client.delete(*keys)
        await client.aclose()
