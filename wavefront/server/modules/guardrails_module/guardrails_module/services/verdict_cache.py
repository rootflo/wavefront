"""Redis-backed shared tier for the guardrails verdict cache.

Bridges flo_ai's ``VerdictCache`` port onto the process-wide ``CacheManager``,
so the SDK keeps knowing nothing about Redis.

What reaches Redis is decided in the SDK, by ``encode_decision``: any decision
carrying a message body is refused, and only the content-free part of a verdict
— action, finding codes, entity types and counts, severity, policy version — is
serialised. That covers every Azure Content Safety verdict, since Azure only
ever allows or blocks. Presidio's redactions carry the rewritten text, so they
stay in the in-process tier and are never written here.

The keys are digests, so an operator reading this cache sees which namespace
and stage an entry belongs to and nothing else about the payload.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from common_module.log.logger import logger
from flo_ai.guardrails import PolicyDecision, decode_decision, encode_decision

#: Entries outlive a policy edit only in the sense that nothing reads them: the
#: policy version is folded into the key digest, so an edit strands the old
#: entries and this TTL is what eventually reclaims them. Also the ceiling on
#: how long a verdict derived from a since-changed adapter build can be served.
DEFAULT_TTL_SECONDS = 3600

#: A cache lookup must never cost more than the check it is avoiding. The
#: pool's own socket_timeout is 60s, which is right for a request that matters
#: and wrong for one whose failure mode is "do the work anyway".
DEFAULT_TIMEOUT_SECONDS = 0.25

#: Consecutive failures before the cache stops being consulted, and for how
#: long. Without this, a Redis outage adds the full timeout to every lookup and
#: every store — and the guardrails path runs one lookup per message per
#: tool-loop iteration, so the per-turn cost of an outage would be measured in
#: seconds rather than in the milliseconds the cache was saving.
DEFAULT_BREAKER_THRESHOLD = 5
DEFAULT_BREAKER_COOLDOWN_SECONDS = 30.0


class _CircuitBreaker:
    """Stops calling a backend that has repeatedly failed, then tries again.

    Deliberately crude: no half-open accounting, no failure-rate window. The
    only thing it has to get right is never leaving the breaker open forever,
    because a cache that gave up permanently after one blip would look exactly
    like a cache that works while quietly billing a provider for every call.
    """

    def __init__(self, threshold: int, cooldown_seconds: float) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        if self._open_until == 0.0:
            return False
        if time.monotonic() >= self._open_until:
            # Cooldown elapsed: let the next call through to test the backend.
            self._open_until = 0.0
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold and self._open_until == 0.0:
            self._open_until = time.monotonic() + self._cooldown
            logger.warning(
                f'Guardrail verdict cache: {self._failures} consecutive Redis '
                f'failures, pausing lookups for {self._cooldown:.0f}s. '
                f'Checks still run; they are just no longer cached.'
            )


class RedisVerdictCache:
    """Shared, content-free tier of the guardrails verdict cache.

    Implements flo_ai's ``VerdictCache``. Every failure path returns a miss:
    this is an optimisation, and one that could fail an inference request would
    be worse than not having it.

    Uses the raw Redis client rather than ``CacheManager.add``/``get_str``
    on purpose. Those retry three times with exponential backoff, which is
    correct for a write whose loss matters and badly wrong here — it would put
    seconds of backoff inside a request whose cache entry is, by definition,
    optional.
    """

    def __init__(
        self,
        cache_manager: Any,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        breaker_threshold: int = DEFAULT_BREAKER_THRESHOLD,
        breaker_cooldown_seconds: float = DEFAULT_BREAKER_COOLDOWN_SECONDS,
    ) -> None:
        self._client = cache_manager.redis
        self._namespace = getattr(cache_manager, 'namespace', '') or ''
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._breaker = _CircuitBreaker(breaker_threshold, breaker_cooldown_seconds)

    def _redis_key(self, key: str) -> str:
        # Mirrors CacheManager's own prefixing, which the raw client bypasses.
        return f'{self._namespace}/guardrail_verdict:{key}'

    async def _call(self, fn, *args) -> Any:
        """Run a blocking Redis call off the loop, under a deadline.

        ``wait_for`` does not cancel the thread — it only stops the request
        waiting on it. The abandoned thread drains when its socket times out,
        which the breaker then keeps from happening on every subsequent call.
        """
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), self._timeout)

    async def get(self, key: str) -> Optional[PolicyDecision]:
        if self._breaker.is_open:
            return None

        try:
            raw = await self._call(self._client.get, self._redis_key(key))
        except Exception as exc:
            self._breaker.record_failure()
            logger.debug(f'Guardrail verdict cache lookup failed: {exc}')
            return None

        self._breaker.record_success()
        if raw is None:
            return None

        if isinstance(raw, bytes):
            # The shared pool sets decode_responses=True, but this must not
            # depend on a setting owned by another module.
            raw = raw.decode('utf-8', errors='replace')

        decision = decode_decision(raw)
        if decision is None:
            logger.debug('Guardrail verdict cache: unreadable entry, treating as miss')
        return decision

    async def store(self, key: str, decision: PolicyDecision) -> None:
        payload = encode_decision(decision)
        if payload is None:
            # Carries a message body. Stays in the in-process tier only.
            return
        if self._breaker.is_open:
            return

        try:
            await self._call(
                lambda: self._client.set(self._redis_key(key), payload, ex=self._ttl)
            )
        except Exception as exc:
            self._breaker.record_failure()
            logger.debug(f'Guardrail verdict cache write failed: {exc}')
            return

        self._breaker.record_success()
