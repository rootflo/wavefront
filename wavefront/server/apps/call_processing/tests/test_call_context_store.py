import asyncio
import json

from call_processing.services.common.context.store import (
    FETCHED,
    JOINED,
    LIVE,
    SAVED,
    CallContextStore,
    context_key,
)

KEY = context_key('agent-1', 'CA123', 'find_account', {'mobile': '+911234567890'})


class FakeRedis:
    """The few async Redis calls the store makes, over a dict."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError('redis down')

    set = delete = get


class CountingFetch:
    def __init__(self, result=None, delay=0.0):
        self.calls = 0
        self.result = result if result is not None else {'name': 'Jane Doe'}
        self.delay = delay

    async def __call__(self):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return self.result


def test_key_hashes_arguments_and_ignores_their_order():
    a = context_key('agent-1', 'CA123', 'tool', {'x': '1', 'mobile': '+911234567890'})
    b = context_key('agent-1', 'CA123', 'tool', {'mobile': '+911234567890', 'x': '1'})

    assert a == b
    assert '1234567890' not in a
    assert a.startswith('vctx/default/agent-1/CA123/tool/')


async def test_repeat_lookup_is_served_from_redis_on_any_pod():
    redis = FakeRedis()
    fetch = CountingFetch()

    first = await CallContextStore(redis).get_or_fetch(KEY, fetch)
    other_pod = await CallContextStore(redis).get_or_fetch(KEY, fetch)

    assert first == other_pod == {'name': 'Jane Doe'}
    assert fetch.calls == 1


async def test_concurrent_lookups_share_one_fetch():
    store = CallContextStore(FakeRedis())
    fetch = CountingFetch(delay=0.05)

    results = await asyncio.gather(
        store.get_or_fetch(KEY, fetch), store.get_or_fetch(KEY, fetch)
    )

    assert results == [{'name': 'Jane Doe'}, {'name': 'Jane Doe'}]
    assert fetch.calls == 1


async def test_slow_running_fetch_falls_back_to_a_live_call():
    store = CallContextStore(FakeRedis(), wait_s=0.05)
    slow = CountingFetch({'from': 'prefetch'}, delay=0.5)
    live = CountingFetch({'from': 'live'})

    prefetch = asyncio.create_task(store.get_or_fetch(KEY, slow))
    await asyncio.sleep(0)
    result = await store.get_or_fetch(KEY, live)

    assert result == {'from': 'live'}
    assert live.calls == 1
    prefetch.cancel()
    # Wait for the cancelled prefetch to finish; its CancelledError is returned
    await asyncio.gather(prefetch, return_exceptions=True)


async def test_redis_down_means_a_live_call_every_time():
    store = CallContextStore(BrokenRedis())
    fetch = CountingFetch()

    assert await store.get_or_fetch(KEY, fetch) == {'name': 'Jane Doe'}
    assert await store.get_or_fetch(KEY, fetch) == {'name': 'Jane Doe'}
    assert fetch.calls == 2


async def test_failed_result_is_not_saved():
    redis = FakeRedis()
    store = CallContextStore(redis)
    fetch = CountingFetch({'success': False, 'status_code': 408})

    await store.get_or_fetch(KEY, fetch)
    await store.get_or_fetch(KEY, fetch)

    assert fetch.calls == 2
    assert KEY not in redis.data


class FailingWriteRedis(FakeRedis):
    """Claims work; saving the result times out."""

    async def set(self, key, value, nx=False, ex=None):
        if not nx:
            raise TimeoutError('redis write timed out')
        return await super().set(key, value, nx=nx, ex=ex)


async def test_failed_save_clears_the_pending_marker():
    redis = FailingWriteRedis()

    result = await CallContextStore(redis).get_or_fetch(KEY, CountingFetch())

    assert result == {'name': 'Jane Doe'}
    # Otherwise the next lookup would wait for a result that never comes
    assert KEY not in redis.data


async def test_waits_for_a_fetch_running_on_another_pod():
    redis = FakeRedis()
    redis.data[KEY] = json.dumps({'pending': True})
    store = CallContextStore(redis, wait_s=1.0)
    fetch = CountingFetch()

    async def other_pod_finishes():
        await asyncio.sleep(0.15)
        redis.data[KEY] = json.dumps({'result': {'from': 'webhook'}})

    asyncio.create_task(other_pod_finishes())
    result = await store.get_or_fetch(KEY, fetch)

    assert result == {'from': 'webhook'}
    assert fetch.calls == 0


async def test_other_pods_failed_fetch_falls_back_to_a_live_call():
    redis = FakeRedis()
    redis.data[KEY] = json.dumps({'pending': True})
    store = CallContextStore(redis, wait_s=1.0)
    fetch = CountingFetch()

    async def other_pod_fails():
        await asyncio.sleep(0.15)
        del redis.data[KEY]

    asyncio.create_task(other_pod_fails())
    result = await store.get_or_fetch(KEY, fetch)

    assert result == {'name': 'Jane Doe'}
    assert fetch.calls == 1


async def test_lookup_says_where_the_answer_came_from():
    redis = FakeRedis()
    fetch = CountingFetch()

    assert (await CallContextStore(redis).lookup(KEY, fetch))[1] == FETCHED
    assert (await CallContextStore(redis).lookup(KEY, fetch))[1] == SAVED
    assert (await CallContextStore(BrokenRedis()).lookup(KEY, fetch))[1] == LIVE


async def test_lookup_during_a_running_fetch_is_joined():
    store = CallContextStore(FakeRedis())
    fetch = CountingFetch(delay=0.05)

    (_, first), (_, second) = await asyncio.gather(
        store.lookup(KEY, fetch), store.lookup(KEY, fetch)
    )

    assert (first, second) == (FETCHED, JOINED)
    assert fetch.calls == 1
