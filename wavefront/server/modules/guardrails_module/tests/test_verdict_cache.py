"""The Redis tier of the guardrails verdict cache.

Two things to prove. That nothing carrying a message body is written — the
reason this tier exists in the shape it does. And that a Redis that is slow,
broken or absent costs a re-evaluation rather than a failed request, because
the cache sits on the path of every inference call.

The rule about content is enforced in flo_ai and tested there against the
decision shapes directly; these tests check that this backend actually honours
it rather than reaching past it.
"""

import time

import pytest
from flo_ai.guardrails import (
    AssessmentStatus,
    CheckResult,
    PolicyAction,
    PolicyDecision,
)
from guardrails_module.services.verdict_cache import (
    RedisVerdictCache,
    _CircuitBreaker,
)

KEY = 'acme:BEFORE_MODEL:abc123'


def allow_decision():
    return PolicyDecision(
        action=PolicyAction.ALLOW,
        observed_action=PolicyAction.ALLOW,
        policy_version='v1',
        results=[
            CheckResult(
                status=AssessmentStatus.PASS,
                action=PolicyAction.ALLOW,
                adapter='azure_content_safety',
            )
        ],
    )


def transform_decision():
    return PolicyDecision(
        action=PolicyAction.TRANSFORM,
        observed_action=PolicyAction.TRANSFORM,
        transformed_content='my number is <PHONE_NUMBER>',
        results=[
            CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.TRANSFORM,
                adapter='presidio_pii',
                transformed_content='my number is <PHONE_NUMBER>',
            )
        ],
    )


class FakeRedis:
    def __init__(self, fail_with=None, delay=0.0, decode=True):
        self.store = {}
        self.expiries = {}
        self.fail_with = fail_with
        self.delay = delay
        self.decode = decode
        self.gets = 0
        self.sets = 0

    def get(self, key):
        self.gets += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail_with:
            raise self.fail_with
        value = self.store.get(key)
        if value is not None and not self.decode:
            return value.encode('utf-8')
        return value

    def set(self, key, value, ex=None):
        self.sets += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail_with:
            raise self.fail_with
        self.store[key] = value
        self.expiries[key] = ex
        return True


class FakeCacheManager:
    def __init__(self, redis, namespace='floware'):
        self.redis = redis
        self.namespace = namespace


def build(redis=None, **kwargs):
    return RedisVerdictCache(FakeCacheManager(redis or FakeRedis()), **kwargs)


class TestWhatIsWritten:
    async def test_a_content_free_verdict_round_trips(self):
        redis = FakeRedis()
        cache = build(redis)

        await cache.store(KEY, allow_decision())
        restored = await cache.get(KEY)

        assert restored is not None
        assert restored.action is PolicyAction.ALLOW
        assert restored.policy_version == 'v1'
        assert restored.results[0].adapter == 'azure_content_safety'

    async def test_a_redaction_is_never_written(self):
        """The guarantee, checked at the backend rather than at the gate."""
        redis = FakeRedis()
        cache = build(redis)

        await cache.store(KEY, transform_decision())

        assert redis.sets == 0
        assert redis.store == {}

    async def test_no_written_value_contains_the_redacted_text(self):
        redis = FakeRedis()
        cache = build(redis)

        await cache.store(KEY, transform_decision())
        await cache.store(KEY, allow_decision())

        assert all('PHONE_NUMBER' not in value for value in redis.store.values())

    async def test_the_ttl_is_applied(self):
        """Policy edits strand entries by changing the key; the TTL reclaims them."""
        redis = FakeRedis()
        cache = build(redis, ttl_seconds=900)

        await cache.store(KEY, allow_decision())

        assert set(redis.expiries.values()) == {900}

    async def test_keys_are_namespaced_like_the_rest_of_the_cache(self):
        """Using the raw client bypasses CacheManager's own prefixing."""
        redis = FakeRedis()
        cache = build(redis)

        await cache.store(KEY, allow_decision())

        [written] = redis.store
        assert written == f'floware/guardrail_verdict:{KEY}'

    async def test_a_byte_response_is_handled(self):
        """decode_responses is set on a pool owned by another module."""
        redis = FakeRedis(decode=False)
        cache = build(redis)

        await cache.store(KEY, allow_decision())

        assert (await cache.get(KEY)) is not None


class TestMisses:
    async def test_an_absent_key_is_a_miss(self):
        assert (await build().get(KEY)) is None

    async def test_an_unreadable_entry_is_a_miss(self):
        redis = FakeRedis()
        redis.store[f'floware/guardrail_verdict:{KEY}'] = 'garbage, not json'

        assert (await build(redis).get(KEY)) is None


class TestFailuresDoNotReachTheRequest:
    async def test_a_broken_backend_reads_as_a_miss(self):
        cache = build(FakeRedis(fail_with=ConnectionError('redis is down')))

        assert (await cache.get(KEY)) is None

    async def test_a_broken_backend_swallows_the_write(self):
        cache = build(FakeRedis(fail_with=ConnectionError('redis is down')))

        await cache.store(KEY, allow_decision())  # must not raise

    async def test_a_slow_backend_gives_up_rather_than_waiting(self):
        """A lookup must never cost more than the check it is avoiding.

        The pool's own socket_timeout is 60s, which would turn a Redis stall
        into a stalled inference request.
        """
        cache = build(FakeRedis(delay=0.3), timeout_seconds=0.01)

        started = time.monotonic()
        result = await cache.get(KEY)

        assert result is None
        assert time.monotonic() - started < 0.2


class TestCircuitBreaker:
    async def test_it_stops_calling_a_backend_that_keeps_failing(self):
        """Otherwise an outage costs the full timeout on every lookup.

        The guardrails path runs one lookup per message per tool-loop
        iteration, so that is seconds per turn rather than the milliseconds
        the cache was there to save.
        """
        redis = FakeRedis(fail_with=ConnectionError('down'))
        cache = build(redis, breaker_threshold=3)

        for _ in range(10):
            await cache.get(KEY)

        assert redis.gets == 3, 'stops after the threshold'

    async def test_a_tripped_breaker_also_skips_writes(self):
        redis = FakeRedis(fail_with=ConnectionError('down'))
        cache = build(redis, breaker_threshold=2)

        for _ in range(5):
            await cache.get(KEY)
        await cache.store(KEY, allow_decision())

        assert redis.sets == 0

    async def test_a_success_resets_the_count(self):
        redis = FakeRedis()
        cache = build(redis, breaker_threshold=2)
        key = f'floware/guardrail_verdict:{KEY}'

        redis.fail_with = ConnectionError('blip')
        await cache.get(KEY)
        redis.fail_with = None
        await cache.get(KEY)

        redis.fail_with = ConnectionError('blip')
        await cache.get(KEY)
        redis.fail_with = None
        await cache.store(KEY, allow_decision())

        assert key in redis.store, 'two isolated blips must not trip the breaker'

    def test_it_reopens_after_the_cooldown(self, monkeypatch):
        """A breaker that never closed would look exactly like a working cache
        while quietly billing a provider for every call."""
        clock = {'now': 1000.0}
        monkeypatch.setattr(
            'guardrails_module.services.verdict_cache.time.monotonic',
            lambda: clock['now'],
        )
        breaker = _CircuitBreaker(threshold=2, cooldown_seconds=30.0)

        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open

        clock['now'] += 29.0
        assert breaker.is_open

        clock['now'] += 2.0
        assert not breaker.is_open


class TestEnvConfiguration:
    @pytest.mark.parametrize(
        'value,expected',
        [('5000', 5000), ('0', 0), ('', 1_000_000), ('nonsense', 1_000_000)],
    )
    def test_the_char_budget_falls_back_on_a_bad_value(
        self, monkeypatch, value, expected
    ):
        """A typo in a tuning knob must not crash a server nor silently
        disable the cache in some third way."""
        from guardrails_module.services.engine_factory import ENV_CACHE_CHARS, _env_int

        monkeypatch.setenv(ENV_CACHE_CHARS, value)

        assert _env_int(ENV_CACHE_CHARS, 1_000_000) == expected

    @pytest.mark.parametrize(
        'value,expected',
        [
            ('false', False),
            ('0', False),
            ('off', False),
            ('true', True),
            ('1', True),
            ('maybe', True),
            ('', True),
        ],
    )
    def test_the_shared_tier_can_be_switched_off(self, monkeypatch, value, expected):
        from guardrails_module.services.engine_factory import (
            ENV_CACHE_SHARED_ENABLED,
            _env_bool,
        )

        monkeypatch.setenv(ENV_CACHE_SHARED_ENABLED, value)

        assert _env_bool(ENV_CACHE_SHARED_ENABLED, True) is expected
