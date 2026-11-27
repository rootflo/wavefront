import contextlib
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    List,
    Optional,
    Union,
)

from common_module.log.logger import logger
from db_repo_module.cache.base_cache import BaseCache
from db_repo_module.cache.base_cache import CacheUnavailableError
from db_repo_module.cache.base_cache import _with_retry
from db_repo_module.cache.lua_scripts import (
    FILL_SCRIPT,
    PENDING_MARKER,
    PENDING_TTL_SECONDS,
    READ_SCRIPT,
    TOKEN_TTL_SECONDS,
)
from redis import ConnectionError
from redis import Redis
from redis import RedisError
from redis import TimeoutError
from redis import asyncio as aioredis

__all__ = ['CacheManager', 'CacheUnavailableError']


class CacheManager(BaseCache):
    async def aget_str(
        self,
        key: str,
        default: Any = None,
        *,
        attempts: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Async ``get_str``. Raises CacheUnavailableError if Redis fails."""
        namespaced = f'{self.namespace}/{key}'

        async def call(client: aioredis.Redis) -> Optional[str]:
            return await client.get(namespaced)

        value = await self._run_async(
            'GET', call, lambda: self.get_str(key), attempts, timeout
        )
        return value if value is not None else default

    async def aadd(
        self,
        key: str,
        value: Union[str, int, float, bytes],
        expiry: int = 3600,
        nx: bool = False,
        *,
        attempts: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Async ``add``. Raises CacheUnavailableError if Redis fails."""
        namespaced = f'{self.namespace}/{key}'

        async def call(client: aioredis.Redis) -> bool:
            return bool(await client.set(namespaced, value, ex=expiry, nx=nx))

        return await self._run_async(
            'SET',
            call,
            lambda: self.add(key, value, expiry=expiry, nx=nx),
            attempts,
            timeout,
        )

    async def aremove(
        self,
        key: str,
        *,
        attempts: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Async ``remove``. Raises CacheUnavailableError if Redis fails."""
        namespaced = f'{self.namespace}/{key}'

        async def call(client: aioredis.Redis) -> bool:
            return bool(await client.delete(namespaced))

        return await self._run_async(
            'DEL', call, lambda: self.remove(key), attempts, timeout
        )

    # Tolerant versions for callers where the cache is an optimisation: a Redis
    # failure is logged and treated as a miss (reads) or a no-op (writes), so
    # the request carries on from the database. A failed remove leaves the old
    # value until its TTL expires; that is logged so it can be traced.

    async def try_aget_str(self, key: str, default: Any = None) -> Optional[str]:
        """``aget_str`` that returns ``default`` when Redis fails."""
        try:
            return await self.aget_str(key, default)
        except CacheUnavailableError as e:
            logger.warning(f'Cache read skipped for {key}: {e}')
            return default

    async def try_aadd(
        self,
        key: str,
        value: Union[str, int, float, bytes],
        expiry: int = 3600,
        nx: bool = False,
    ) -> bool:
        """``aadd`` that returns False when Redis fails."""
        try:
            return await self.aadd(key, value, expiry=expiry, nx=nx)
        except CacheUnavailableError as e:
            logger.warning(f'Cache write skipped for {key}: {e}')
            return False

    async def try_aremove(self, key: str) -> bool:
        """``aremove`` that returns False when Redis fails."""
        try:
            return await self.aremove(key)
        except CacheUnavailableError as e:
            logger.warning(
                f'Cache delete failed for {key}; it may be stale until it expires: {e}'
            )
            return False

    # ------------------------------------------------------------------
    # Generation-checked cache-aside (read_through / invalidating)
    #
    # The protocol and its Lua scripts are described in lua_scripts.py.
    # ------------------------------------------------------------------

    async def read_through(
        self,
        key: str,
        loader: Callable[[], Awaitable[Optional[str]]],
        *,
        ttl: int,
    ) -> Optional[str]:
        """The cached value for ``key``, or ``loader()`` from the source of truth.

        ``loader`` returns the string to cache, or None for "not found" (not
        cached). Redis failures never fail the read: the loader's value is
        returned and the fill is skipped. ``loader`` runs at most once, and its
        own errors propagate.
        """
        value_key, gen_key = self._rt_keys(key)
        args = (
            value_key,
            gen_key,
            self._rt_writers_key(key),
            self._new_token(),
            TOKEN_TTL_SECONDS,
        )
        token: Optional[str] = None
        try:

            async def read(client: aioredis.Redis) -> Any:
                return await client.eval(READ_SCRIPT, 3, *args)

            def read_sync() -> Any:
                return self.redis.eval(READ_SCRIPT, 3, *args)

            raw_token, raw_value = await self._run_async(
                'READ', read, read_sync, attempts=1, timeout=None
            )
        except CacheUnavailableError as e:
            logger.warning(f'Cache read skipped for {key}: {e}')
        else:
            token, cached = self._as_str(raw_token), self._as_str(raw_value)
            if token is not None and token.startswith(PENDING_MARKER):
                # A change is in flight (or its final rotation failed): read
                # the source of truth and don't cache what we read.
                token = None
            elif cached is not None:
                tag, _, payload = cached.partition('\n')
                if tag == token:
                    return payload

        value = await loader()
        if value is None or token is None:
            return value
        try:

            async def fill(client: aioredis.Redis) -> Any:
                return await client.eval(
                    FILL_SCRIPT, 2, value_key, gen_key, token, value, ttl
                )

            def fill_sync() -> Any:
                return self.redis.eval(
                    FILL_SCRIPT, 2, value_key, gen_key, token, value, ttl
                )

            await self._run_async('FILL', fill, fill_sync, attempts=1, timeout=None)
        except CacheUnavailableError as e:
            logger.warning(f'Cache fill skipped for {key}: {e}')
        return value

    @contextlib.asynccontextmanager
    async def invalidating(self, *keys: str) -> AsyncIterator[None]:
        """Wrap a change to the source of truth behind ``keys``.

        Before the body: registers this writer and marks the keys pending,
        strictly. If Redis is down this raises CacheUnavailableError (a 503) and
        the body never runs, so nothing has changed and a retry is safe. While
        pending, reads bypass the cache. After the body (success or failure):
        this writer leaves, and the last writer out sets a fresh token,
        best-effort. If that fails the keys stay uncacheable until the marker
        expires, which is safe.
        """
        if not keys:
            yield
            return
        writer = self._new_token()
        await self._rotate(keys, pending=True, writer=writer)
        try:
            yield
        finally:
            try:
                await self._rotate(keys, pending=False, writer=writer)
            except CacheUnavailableError as e:
                logger.warning(
                    f'Cache rotation after a change failed for {keys}; these keys '
                    f'bypass the cache for up to {PENDING_TTL_SECONDS}s: {e}'
                )

    @_with_retry
    def add(
        self,
        key: str,
        value: Union[str, int, float, bytes],
        expiry: int = 3600,
        nx: bool = False,
    ) -> bool:
        try:
            logger.info(f'Adding key: {key} to cache with expiry: {expiry} seconds')
            return bool(
                self.redis.set(f'{self.namespace}/{key}', value, ex=expiry, nx=nx)
            )
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error adding key: {key} to cache: {e}')
            raise

    @_with_retry
    def get_str(self, key: str, default: Any = None) -> Optional[str]:
        try:
            value = self.redis.get(f'{self.namespace}/{key}')
            return value if value is not None else default

        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error getting key: {key} from cache: {e}')
            raise

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.get_str(key, default)
        return int(value) if value is not None else default

    @_with_retry
    def pop_str(self, key: str, default: Any = None) -> Optional[str]:
        """GETDEL when available; otherwise a GET+DEL pipeline."""
        namespaced = f'{self.namespace}/{key}'
        try:
            getdel = getattr(self.redis, 'getdel', None)
            if callable(getdel):
                value = getdel(namespaced)
            else:
                pipe = self.redis.pipeline()
                pipe.get(namespaced)
                pipe.delete(namespaced)
                value, _ = pipe.execute()
            return value if value is not None else default
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error popping key: {key} from cache: {e}')
            raise

    @_with_retry
    def incr_with_expiry(self, key: str, expiry: int) -> int:
        """INCR a fixed-window counter. EXPIRE NX opens the window on first hit."""
        namespaced = f'{self.namespace}/{key}'
        try:
            pipe = self.redis.pipeline()
            pipe.incr(namespaced)
            pipe.expire(namespaced, expiry, nx=True)
            count, _ = pipe.execute()
            return int(count)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error incrementing key: {key} in cache: {e}')
            raise

    # Retries on the same terms as add()/get_str(). A dropped delete is the one
    # failure that outlives the request: the key keeps serving the pre-write
    # value until its TTL expires, so a transient blip here means stale reads
    # long after the blip is over.
    @_with_retry
    def remove(self, key: str) -> bool:
        try:
            return bool(self.redis.delete(f'{self.namespace}/{key}'))
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error removing key: {key} from cache: {e}')
            raise

    _INVALIDATE_BATCH = 500

    def invalidate_query(self, pattern: str) -> int:
        """Remove all keys matching the given pattern (SCAN, not KEYS)."""
        try:
            search_pattern = f'{self.namespace}/{pattern}'
            deleted = 0
            batch: List[str] = []
            for key in self.redis.scan_iter(
                match=search_pattern, count=self._INVALIDATE_BATCH
            ):
                batch.append(key)
                if len(batch) >= self._INVALIDATE_BATCH:
                    deleted += self.redis.delete(*batch)
                    batch.clear()
            if batch:
                deleted += self.redis.delete(*batch)

            if deleted:
                logger.info(
                    f'Invalidated {deleted} cache keys matching pattern: {pattern}'
                )
            else:
                logger.info(f'No cache keys found matching pattern: {pattern}')
            return deleted
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error removing keys with pattern: {pattern} from cache: {e}')
            raise

    @_with_retry
    def publish(self, channel: str, message: str) -> int:
        """
        Publish a message to a Redis channel.

        Args:
            channel: The channel name to publish to
            message: The message to publish

        Returns:
            Number of subscribers that received the message

        Raises:
            RedisError: If publishing fails
        """
        try:
            full_channel = f'{self.namespace}/{channel}'
            logger.info(f'Publishing message to channel: {full_channel}')
            return self.redis.publish(full_channel, message)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error publishing to channel {channel}: {e}')
            raise

    def subscribe(
        self, channels: Optional[List[str]] = None, patterns: Optional[List[str]] = None
    ):
        """
        Subscribe to Redis channels or patterns.

        Args:
            channels: List of channel names to subscribe to
            patterns: List of patterns to subscribe to (supports wildcards)

        Returns:
            PubSub object that can be used to listen for messages

        Example:
            # Subscribe to specific channels
            pubsub = cache_manager.subscribe(channels=['updates', 'notifications'])

            # Subscribe to patterns
            pubsub = cache_manager.subscribe(patterns=['user:*', 'event:*'])

            # Listen for messages
            for message in pubsub.listen():
                if message['type'] == 'message':
                    print(f"Received: {message['data']}")
        """
        try:
            pubsub = Redis(connection_pool=self._get_pubsub_pool()).pubsub()

            if channels:
                namespaced_channels = [f'{self.namespace}/{ch}' for ch in channels]
                pubsub.subscribe(*namespaced_channels)
                logger.info(f'Subscribed to channels: {namespaced_channels}')

            if patterns:
                namespaced_patterns = [f'{self.namespace}/{pat}' for pat in patterns]
                pubsub.psubscribe(*namespaced_patterns)
                logger.info(f'Subscribed to patterns: {namespaced_patterns}')

            if not channels and not patterns:
                logger.warning('No channels or patterns specified for subscription')

            return pubsub
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error subscribing to channels/patterns: {e}')
            raise

    # ------------------------------------------------------------------
    # Redis Streams
    # ------------------------------------------------------------------

    @_with_retry
    def xadd(self, stream: str, fields: dict, maxlen: int = 10000) -> str:
        """Append an entry to a Redis Stream. Returns the message ID."""
        try:
            return self.redis.xadd(f'{self.namespace}/{stream}', fields, maxlen=maxlen)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error appending to stream {stream}: {e}')
            raise

    def xgroup_create(
        self, stream: str, group: str, id: str = '$', mkstream: bool = True
    ) -> None:
        """Create a consumer group. Silently ignores BUSYGROUP if already exists."""
        try:
            self.redis.xgroup_create(
                f'{self.namespace}/{stream}', group, id=id, mkstream=mkstream
            )
            logger.info(f'Created consumer group {group} on stream {stream}')
        except Exception as e:
            if 'BUSYGROUP' in str(e):
                logger.debug(
                    f'Consumer group {group} already exists on stream {stream}'
                )
            else:
                logger.error(f'Error creating consumer group {group}: {e}')
                raise

    @_with_retry
    def xread_group(
        self,
        group: str,
        consumer: str,
        streams: dict,
        count: int = 10,
        block_ms: Optional[int] = 1000,
    ) -> list:
        """Read messages from stream(s) via consumer group.

        Args:
            streams: mapping of stream_name → '>' (undelivered) or message ID (pending)
            block_ms: how long Redis may hold the call open waiting for
                messages. The pooled connection is busy for that whole time,
                so long-running pollers should pass None (return at once) and
                sleep between polls instead. Note 0 means block forever.
        """
        try:
            namespaced = {f'{self.namespace}/{k}': v for k, v in streams.items()}
            return (
                self.redis.xreadgroup(
                    group, consumer, namespaced, count=count, block=block_ms
                )
                or []
            )
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error reading from stream group {group}: {e}')
            raise

    @_with_retry
    def xack(self, stream: str, group: str, *message_ids: str) -> int:
        """Acknowledge one or more messages in a consumer group."""
        try:
            return self.redis.xack(f'{self.namespace}/{stream}', group, *message_ids)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error acknowledging messages on stream {stream}: {e}')
            raise

    @_with_retry
    def xpending_range(
        self,
        stream: str,
        group: str,
        count: int,
        min_idle_ms: Optional[int] = None,
        consumer: Optional[str] = None,
        start: str = '-',
        end: str = '+',
    ) -> list:
        """Pending (delivered, unacknowledged) entries of a consumer group:
        dicts with message_id, consumer, time_since_delivered (ms) and
        times_delivered. min_idle_ms / consumer narrow the result."""
        try:
            return self.redis.xpending_range(
                f'{self.namespace}/{stream}',
                group,
                min=start,
                max=end,
                count=count,
                consumername=consumer,
                idle=min_idle_ms,
            )
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error listing pending entries on stream {stream}: {e}')
            raise

    @_with_retry
    def xautoclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_ms: int,
        start_id: str = '0-0',
        count: Optional[int] = None,
    ) -> list:
        """Claim entries pending longer than min_idle_ms (from any consumer)
        for `consumer`. Returns [(message_id, fields), ...]; entries deleted
        from the stream meanwhile are dropped from the pending list by Redis."""
        try:
            result = self.redis.xautoclaim(
                f'{self.namespace}/{stream}',
                group,
                consumer,
                min_idle_ms,
                start_id=start_id,
                count=count,
            )
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.warning(f'Error claiming idle entries on stream {stream}: {e}')
            raise
        # [next_start_id, claimed, deleted_ids] (Redis 7) or the first two (6.2)
        return result[1] if result and len(result) > 1 else []
