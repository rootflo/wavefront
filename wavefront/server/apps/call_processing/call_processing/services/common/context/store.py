"""Per-call memory for read-only tool results, shared by every pod through Redis.

A result is fetched once per call: a repeat lookup returns the saved result,
and a lookup made while the same fetch is still running waits for it instead
of firing a second request. A prefetch at call start (compiler.py) and the
AI's later tool call meet on the same key.

Never slower than today: any Redis error counts as a miss, and a wait on
someone else's fetch gives up after ``WAIT_FOR_FETCH_S`` and makes the live
call. The client is ``redis.asyncio`` with a short timeout and no retries;
``CacheManager`` is sync and retries for seconds, which would freeze a call
during a Redis outage.
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from redis.asyncio import Redis

from call_processing.log.logger import logger

# Customer data stays in Redis this long (D7: acceptable for the first pass)
CONTEXT_TTL_S = 15 * 60
# How long a lookup waits for a fetch someone else already started (D4)
WAIT_FOR_FETCH_S = 2.5
# A fetch that dies without clearing its marker stops blocking others after this
_PENDING_TTL_S = 10
_POLL_INTERVAL_S = 0.1
_REDIS_TIMEOUT_S = 0.15
_REDIS_CONNECT_TIMEOUT_S = 0.5
# No tenants in call_processing yet (D2); the key keeps a slot for one
_DEFAULT_TENANT = 'default'

_PENDING = {'pending': True}
# Waiters on an in-process fetch get this when it produced nothing to share
_NO_RESULT = object()
# A read that failed: skip the claim and the write, so an outage costs one timeout
_UNAVAILABLE = object()

Fetch = Callable[[], Awaitable[Any]]

# Where a lookup's answer came from
SAVED = 'saved'  # a result saved earlier in this call: no API call
JOINED = 'joined'  # a fetch already running (the prefetch, say): no extra API call
FETCHED = 'fetched'  # this lookup called the API and saved the result
LIVE = 'live'  # called the API without the store (Redis down, or a wait timed out)

_OUTCOME_LOG = {
    SAVED: 'hit, API call skipped (saved result from Redis)',
    JOINED: 'hit, API call skipped (joined a fetch already running)',
    FETCHED: 'miss, called the API and saved the result',
    LIVE: 'miss, called the API (store unavailable or wait timed out)',
}


def is_failure(result: Any) -> bool:
    """Tool wrappers report errors as ``{'success': False, ...}``; never cache those."""
    return isinstance(result, dict) and result.get('success') is False


def context_key(
    agent_id: str,
    call_ref: str,
    tool_name: str,
    args: Dict[str, Any],
    tenant_id: str = _DEFAULT_TENANT,
) -> str:
    """Scoped key; the arguments (which hold the phone number) only as a hash."""
    canonical = json.dumps(args, sort_keys=True, separators=(',', ':'), default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f'vctx/{tenant_id}/{agent_id}/{call_ref}/{tool_name}/{digest}'


def create_context_redis(
    *,
    host: str,
    port: int,
    protocol: str,
    password: Optional[str],
    db: int,
    pool_size: Optional[int] = None,
) -> Redis:
    """Async client for the store: CacheManager's server, fail-fast settings."""
    port = int(port)
    return Redis(
        host=host,
        port=port,
        db=int(db),
        password=password or None,
        # Same SSL rule as CacheManager
        ssl=protocol == 'rediss' or port == 10000,
        socket_timeout=_REDIS_TIMEOUT_S,
        socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_S,
        max_connections=int(pool_size) if pool_size is not None else 10,
        decode_responses=True,
    )


class CallContextStore:
    def __init__(
        self,
        redis: Redis,
        ttl_s: int = CONTEXT_TTL_S,
        wait_s: float = WAIT_FOR_FETCH_S,
    ):
        self._redis = redis
        self._ttl_s = ttl_s
        self._wait_s = wait_s
        # Same-pod single-flight: key -> the running fetch's result
        self._in_flight: Dict[str, asyncio.Future] = {}

    async def get_or_fetch(self, key: str, fetch: Fetch) -> Any:
        """The saved result for ``key``, or ``fetch()``'s (saved when it succeeds)."""
        result, _ = await self.lookup(key, fetch)
        return result

    async def lookup(self, key: str, fetch: Fetch) -> Tuple[Any, str]:
        """Like ``get_or_fetch``, plus where the answer came from (``SAVED`` …)."""
        running = self._in_flight.get(key)
        if running is not None:
            try:
                result = await asyncio.wait_for(asyncio.shield(running), self._wait_s)
            except asyncio.TimeoutError:
                result = _NO_RESULT
            if result is _NO_RESULT or is_failure(result):
                return await fetch(), LIVE
            return result, JOINED

        # Registered before the first await, so a concurrent lookup finds it
        future = asyncio.get_running_loop().create_future()
        self._in_flight[key] = future
        result = _NO_RESULT
        try:
            result, source = await self._resolve(key, fetch)
            return result, source
        finally:
            self._in_flight.pop(key, None)
            future.set_result(result)

    async def _resolve(self, key: str, fetch: Fetch) -> Tuple[Any, str]:
        saved = await self._read(key)
        if saved is _UNAVAILABLE:
            return await fetch(), LIVE
        if saved is None:
            if await self._claim(key):
                return await self._fetch(key, fetch), FETCHED
            saved = _PENDING  # another pod claimed it a moment ago
        if 'result' in saved:
            return saved['result'], SAVED
        # Another pod is fetching (the Twilio webhook, say): wait for it
        saved = await self._poll(key)
        if saved is not None:
            return saved['result'], JOINED
        return await self._fetch(key, fetch), FETCHED

    async def _fetch(self, key: str, fetch: Fetch) -> Any:
        try:
            result = await fetch()
        except BaseException:
            await self._delete(key)
            raise
        if is_failure(result):
            await self._delete(key)
        else:
            await self._write(key, result)
        return result

    async def _poll(self, key: str) -> Optional[Dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + self._wait_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)
            saved = await self._read(key)
            if saved is None or saved is _UNAVAILABLE:
                return None  # the other fetch failed or Redis is down
            if 'result' in saved:
                return saved
        return None

    # ------------------------------------------------------- Redis, fail-open

    async def _read(self, key: str) -> Any:
        """The saved dict, None on a miss, ``_UNAVAILABLE`` on a Redis error."""
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f'Call context read failed, fetching live: {e}')
            return _UNAVAILABLE

    async def _claim(self, key: str) -> bool:
        """Mark a fetch as running; False if another pod already did."""
        try:
            return bool(
                await self._redis.set(
                    key, json.dumps(_PENDING), nx=True, ex=_PENDING_TTL_S
                )
            )
        except Exception as e:
            logger.warning(f'Call context claim failed, fetching live: {e}')
            return True

    async def _write(self, key: str, result: Any) -> None:
        try:
            await self._redis.set(key, json.dumps({'result': result}), ex=self._ttl_s)
        except Exception as e:
            logger.warning(f'Call context write failed: {e}')

    async def _delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.warning(f'Call context delete failed: {e}')


@dataclass(frozen=True)
class ToolCache:
    """One read-only tool on one call."""

    store: CallContextStore
    agent_id: str
    call_ref: str
    tool_name: str

    def key(self, args: Dict[str, Any]) -> str:
        return context_key(self.agent_id, self.call_ref, self.tool_name, args)

    async def run(self, args: Dict[str, Any], fetch: Fetch) -> Any:
        result, _ = await self.lookup(args, fetch)
        return result

    async def lookup(self, args: Dict[str, Any], fetch: Fetch) -> Tuple[Any, str]:
        """The result and where it came from, logged as a hit or a miss."""
        key = self.key(args)
        started = time.monotonic()
        result, source = await self.store.lookup(key, fetch)
        # The key matches the "Prefetch done" line's when this used the prefetch
        logger.info(
            f'Call context {_OUTCOME_LOG[source]}: tool {self.tool_name!r}, '
            f'call {self.call_ref}, {round((time.monotonic() - started) * 1000)}ms, '
            f'key {key}'
        )
        return result, source
