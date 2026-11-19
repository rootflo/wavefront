import asyncio
import contextlib
import functools
import socket
import threading
import time
import uuid
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    List,
    Optional,
    TypeVar,
    Union,
)

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from db_repo_module.cache.redis_settings import RedisSettings
from redis import Connection
from redis import ConnectionError
from redis import BlockingConnectionPool
from redis import ConnectionPool
from redis import Redis
from redis import RedisError
from redis import SSLConnection
from redis import TimeoutError
from redis import asyncio as aioredis
from redis.exceptions import OutOfMemoryError
from tenacity import AsyncRetrying
from tenacity import RetryError
from tenacity import Retrying
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential

F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')


class CacheUnavailableError(RedisError):
    """An a* call failed: Redis errored, timed out, or ran out of retries.

    One exception type for callers that want to fall back (e.g. to the
    database) whatever the cause.
    """


# The pubsub listener holds one connection per subscribe() call for its whole
# life; floware subscribes once per worker.
_PUBSUB_MAX_CONNECTIONS = 4


def _is_retryable_redis_error(exc: BaseException) -> bool:
    """Retry everything except OOM, which fails the same way every time."""
    if isinstance(exc, OutOfMemoryError):
        return False
    return isinstance(exc, (RedisError, ConnectionError, TimeoutError))


def _with_retry(method: F) -> F:
    """Retry a CacheManager method with the instance's settings.

    A plain tenacity ``@retry`` is bound when the class is defined, so it could
    not read the [redis] settings. Each call gets a fresh copy of the policy,
    the same way tenacity's own decorator does.
    """

    @functools.wraps(method)
    def wrapper(self: 'CacheManager', *args: Any, **kwargs: Any) -> Any:
        return self._retry_policy.copy()(method, self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def _pubsub_keepalive_options() -> dict[int, int]:
    """TCP keepalive tuned to notice a dead pubsub connection in about a minute.

    The pubsub socket has no read timeout (it waits for messages indefinitely),
    so keepalive is what detects a silently dropped connection. Options the OS
    does not offer are skipped.
    """
    options = {}
    for name, value in (
        ('TCP_KEEPIDLE', 30),
        ('TCP_KEEPINTVL', 10),
        ('TCP_KEEPCNT', 3),
    ):
        option = getattr(socket, name, None)
        if option is not None:
            options[option] = value
    return options


class CacheManager(CommonCache):
    def __init__(
        self,
        namespace: str = '',
        settings: RedisSettings | None = None,
    ):
        """
        Args:
            settings: Redis connection, pool, and retry settings. Defaults match
                [redis] ini defaults (localhost, pool_size 20, pool_timeout 2s).
                pool_size is a per-process cap; when every connection is busy,
                callers wait up to pool_timeout then get
                ConnectionError('No connection available.').
                max_retries is the total number of attempts per call;
                initial_backoff/max_backoff bound the wait between them.
        """
        redis = settings or RedisSettings()
        self.namespace = namespace
        self.max_retries = int(redis.max_retries)
        self.initial_backoff = float(redis.initial_backoff)
        self.max_backoff = float(redis.max_backoff)
        self._redis_host = redis.host
        self._redis_port = int(redis.port)
        self._redis_protocol = redis.protocol
        self._redis_password = redis.password
        self._redis_db = int(redis.db)
        self._pool_timeout = float(redis.pool_timeout)
        self._connection_timeout = float(redis.connection_timeout)

        self._retry_policy = Retrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=self.initial_backoff,
                min=self.initial_backoff,
                max=self.max_backoff,
            ),
            retry=retry_if_exception(_is_retryable_redis_error),
        )

        self.pool = self._create_connection_pool(
            connection_timeout=self._connection_timeout,
            socket_timeout=float(redis.socket_timeout),
            socket_keepalive=bool(redis.socket_keepalive),
            pool_size=int(redis.pool_size),
        )
        self.redis = self._create_redis_connection()

        # Created on first subscribe(); see _get_pubsub_pool.
        self._pubsub_pool: Optional[ConnectionPool] = None
        self._pubsub_pool_lock = threading.Lock()

        # Async client for the a* methods; created by bind_event_loop().
        self._socket_timeout = float(redis.socket_timeout)
        self._async_pool_size = int(redis.async_pool_size)
        self.async_command_timeout = float(redis.async_command_timeout)
        self._async_redis: Optional[aioredis.Redis] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        # Test the connection immediately - fail fast if Redis is unreachable
        try:
            self.redis.ping()
            logger.info('Connected to Redis with redis ping')
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.error(f'Failed to connect to Redis during initialization: {e}')
            logger.error('Server will not start without Redis connectivity')
            raise RuntimeError(f'Redis connection test failed: {e}') from e

    def _connection_kwargs(
        self,
        connection_timeout: float,
        socket_timeout: Optional[float],
        socket_keepalive: bool,
    ) -> dict:
        host = self._redis_host
        port = self._redis_port
        protocol = self._redis_protocol
        password = self._redis_password

        connection_class = Connection
        if protocol == 'rediss' or port == 10000:
            logger.info(f'Using SSLConnection for Redis (Port: {port})')
            connection_class = SSLConnection

        pool_kwargs = {
            'connection_class': connection_class,
            'host': host,
            'port': port,
            'db': self._redis_db,
            'socket_timeout': socket_timeout,
            'socket_keepalive': socket_keepalive,
            'socket_connect_timeout': connection_timeout,
            # Off: redis-py would retry a timed-out command once more on its own,
            # doubling every wait. Retries come only from _retry_policy, so the
            # worst case stays max_retries x socket_timeout plus the backoff.
            'retry_on_timeout': False,
            'health_check_interval': 30,
            'encoding': 'utf-8',
            'decode_responses': True,
            # Azure Managed Redis drops the connection on CLIENT SETINFO rather
            # than returning a RESP error, which redis-py 5.x doesn't handle —
            # the dropped socket triggers a reconnect loop that hits Python's
            # recursion limit. Empty strings skip the command entirely.
            'lib_name': '',
            'lib_version': '',
        }

        if password:
            pool_kwargs['password'] = password
        return pool_kwargs

    def _create_connection_pool(
        self,
        connection_timeout: float,
        socket_timeout: float,
        socket_keepalive: bool,
        pool_size: int,
    ) -> ConnectionPool:
        try:
            pool_kwargs = self._connection_kwargs(
                connection_timeout, socket_timeout, socket_keepalive
            )
            # Blocking: when every connection is busy, wait briefly for one to
            # be released instead of failing at once with 'Too many connections'.
            return BlockingConnectionPool(
                timeout=self._pool_timeout, max_connections=pool_size, **pool_kwargs
            )
        except Exception as e:
            logger.error(f'Failed to create connection pool: {e}s')
            raise

    def _get_pubsub_pool(self) -> ConnectionPool:
        """Separate pool for pubsub, with no read timeout.

        A subscriber waits on its socket until a message arrives, which can be
        a long time. With the main pool's short socket_timeout an idle
        subscriber would reconnect every few seconds, and a message published
        during a reconnect is lost (pubsub does not store messages). The
        listener runs on its own thread, so blocking there never stalls the
        event loop. TCP keepalive detects a dead connection instead.
        """
        with self._pubsub_pool_lock:
            if self._pubsub_pool is None:
                pool_kwargs = self._connection_kwargs(
                    self._connection_timeout, socket_timeout=None, socket_keepalive=True
                )
                pool_kwargs['socket_keepalive_options'] = _pubsub_keepalive_options()
                # On here: redis-py retries a timed-out pubsub read once,
                # reconnecting and resubscribing. It covers TimeoutError only.
                # A Redis restart raises ConnectionError, which still ends the
                # listener thread; restarting the listener is a separate fix.
                pool_kwargs['retry_on_timeout'] = True
                self._pubsub_pool = ConnectionPool(
                    max_connections=_PUBSUB_MAX_CONNECTIONS, **pool_kwargs
                )
            return self._pubsub_pool

    # ------------------------------------------------------------------
    # Async client (a* methods)
    # ------------------------------------------------------------------
    #
    # The sync methods above block the thread that calls them; from async code
    # that is the event loop, so a slow Redis stalls every request in the
    # worker. The a* methods wait on the loop instead.
    #
    # An asyncio client belongs to the loop it was created on, and scheduled
    # jobs run on loops of their own (asyncio.run on the APScheduler thread).
    # So the client is bound to the app's main loop by bind_event_loop(), and
    # an a* call from any other loop (or before binding) runs the sync method
    # on a worker thread instead. Callers don't need to know which they get.

    def bind_event_loop(self) -> None:
        """Create the async client on the running loop. Call once at app startup."""
        loop = asyncio.get_running_loop()
        if self._async_redis is not None:
            return
        kwargs = self._connection_kwargs(
            self._connection_timeout, self._socket_timeout, socket_keepalive=True
        )
        kwargs['connection_class'] = (
            aioredis.SSLConnection
            if kwargs['connection_class'] is SSLConnection
            else aioredis.Connection
        )
        pool = aioredis.BlockingConnectionPool(
            max_connections=self._async_pool_size, timeout=self._pool_timeout, **kwargs
        )
        self._async_redis = aioredis.Redis(connection_pool=pool)
        self._async_loop = loop
        logger.info(
            f'Async Redis client ready (pool {self._async_pool_size}, '
            f'call timeout {self.async_command_timeout:g}s)'
        )

    async def aclose(self) -> None:
        """Close the async client. Call on the loop it was bound to."""
        client, self._async_redis, self._async_loop = self._async_redis, None, None
        if client is not None:
            await client.aclose()

    async def _run_async(
        self,
        name: str,
        call: Callable[[aioredis.Redis], Awaitable[T]],
        sync_fallback: Callable[[], T],
        attempts: Optional[int],
        timeout: Optional[float],
    ) -> T:
        """Run ``call`` on the async client with retries and an overall time limit.

        Every failure (Redis error, timeout, retries exhausted) is raised as
        CacheUnavailableError.
        """
        limit = self.async_command_timeout if timeout is None else timeout
        try:
            if (
                self._async_redis is None
                or asyncio.get_running_loop() is not self._async_loop
            ):
                return await asyncio.wait_for(asyncio.to_thread(sync_fallback), limit)

            client = self._async_redis
            retrying = AsyncRetrying(
                stop=stop_after_attempt(attempts or self.max_retries),
                wait=wait_exponential(
                    multiplier=self.initial_backoff,
                    min=self.initial_backoff,
                    max=self.max_backoff,
                ),
                retry=retry_if_exception(_is_retryable_redis_error),
            )

            async def with_retries() -> T:
                return await retrying(call, client)

            return await asyncio.wait_for(with_retries(), limit)
        except (
            asyncio.TimeoutError,
            RetryError,
            RedisError,
            ConnectionError,
            TimeoutError,
        ) as e:
            raise CacheUnavailableError(
                f'Redis {name} failed: {type(e).__name__}: {e}'
            ) from e

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
    # Plain get / fill / delete has a race once reads await: a reader loads
    # the old value from the source, a writer commits and deletes the key,
    # then the reader's late fill puts the old value back. NX fills don't help
    # (the key is absent after the delete). Instead every key K has a random
    # token in G(K):
    #   - a reader captures the token BEFORE loading the source, and fills only
    #     if the token is unchanged (atomic compare-and-set in Lua); a hit is
    #     valid only if the value carries the current token;
    #   - a writer replaces the token strictly before its change (Redis down:
    #     CacheUnavailableError, a 503, nothing changed) and again best-effort
    #     after it (defeats a reader that captured the token in between). It
    #     never writes the new value; the next read fills it.
    # A missing token never validates anything (the read creates a fresh one),
    # so correctness does not depend on any TTL or eviction policy. Keys live
    # under a separate ``rt/`` prefix, and K and G(K) share a {hash tag}.
    # ------------------------------------------------------------------

    _RT_GENERATION_TTL = 86400  # seconds; affects hit rate only, never correctness

    _RT_READ = """
local token = redis.call('GET', KEYS[2])
if not token then
  token = ARGV[1]
  redis.call('SET', KEYS[2], token, 'EX', ARGV[2])
end
return {token, redis.call('GET', KEYS[1])}
"""

    _RT_FILL = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then
  return 0
end
redis.call('SET', KEYS[1], ARGV[1] .. '\\n' .. ARGV[2], 'EX', ARGV[3])
return 1
"""

    def _rt_keys(self, key: str) -> tuple[str, str]:
        base = f'{self.namespace}/rt/{{{key}}}'
        return base, f'{base}:gen'

    @staticmethod
    def _new_token() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _as_str(value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        return value.decode('utf-8')

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
        returned and the fill is skipped.
        """
        value_key, gen_key = self._rt_keys(key)
        token: Optional[str] = None
        try:
            new_token = self._new_token()

            async def read(client: aioredis.Redis) -> Any:
                return await client.eval(
                    self._RT_READ,
                    2,
                    value_key,
                    gen_key,
                    new_token,
                    self._RT_GENERATION_TTL,
                )

            def read_sync() -> Any:
                return self.redis.eval(
                    self._RT_READ,
                    2,
                    value_key,
                    gen_key,
                    new_token,
                    self._RT_GENERATION_TTL,
                )

            raw_token, raw_value = await self._run_async(
                'READ', read, read_sync, attempts=1, timeout=None
            )
            token, cached = self._as_str(raw_token), self._as_str(raw_value)
            if cached is not None:
                tag, _, payload = cached.partition('\n')
                if tag == token:
                    return payload
        except CacheUnavailableError as e:
            logger.warning(f'Cache read skipped for {key}: {e}')
            return await loader()

        value = await loader()
        if value is None or token is None:
            return value
        try:

            async def fill(client: aioredis.Redis) -> Any:
                return await client.eval(
                    self._RT_FILL, 2, value_key, gen_key, token, value, ttl
                )

            def fill_sync() -> Any:
                return self.redis.eval(
                    self._RT_FILL, 2, value_key, gen_key, token, value, ttl
                )

            await self._run_async('FILL', fill, fill_sync, attempts=1, timeout=None)
        except CacheUnavailableError as e:
            logger.warning(f'Cache fill skipped for {key}: {e}')
        return value

    async def _rotate(self, keys: tuple[str, ...]) -> None:
        """Give each key a new token and drop its value. Raises on failure.

        Also deletes the plain ``get_str``/``add`` key of the same name, so code
        (or old workers mid-deploy) still using the plain API never keeps
        serving a value this change made stale.
        """
        for key in keys:
            value_key, gen_key = self._rt_keys(key)
            plain_key = f'{self.namespace}/{key}'
            token = self._new_token()

            async def rotate(client: aioredis.Redis) -> Any:
                pipe = client.pipeline(transaction=False)
                pipe.set(gen_key, token, ex=self._RT_GENERATION_TTL)
                pipe.delete(value_key)
                pipe.delete(plain_key)
                return await pipe.execute()

            def rotate_sync() -> Any:
                pipe = self.redis.pipeline(transaction=False)
                pipe.set(gen_key, token, ex=self._RT_GENERATION_TTL)
                pipe.delete(value_key)
                pipe.delete(plain_key)
                return pipe.execute()

            await self._run_async('ROTATE', rotate, rotate_sync, None, None)

    @contextlib.asynccontextmanager
    async def invalidating(self, *keys: str) -> AsyncIterator[None]:
        """Wrap a change to the source of truth behind ``keys``.

        Before the body: strict. If Redis is down this raises
        CacheUnavailableError (a 503) and the body never runs, so nothing has
        changed and a retry is safe. After the body (success or failure):
        best-effort, closing the window for a reader that loaded the old value
        while the change was in flight.
        """
        await self._rotate(keys)
        try:
            yield
        finally:
            try:
                await self._rotate(keys)
            except CacheUnavailableError as e:
                logger.warning(
                    f'Cache invalidation after a change failed for {keys}; a read '
                    f'racing the change could serve the old value until its TTL: {e}'
                )

    def _create_redis_connection(self) -> Redis:
        logger.info('Creating Redis connection from pool...')
        return Redis(connection_pool=self.pool)

    def _checking_redis_connection(self):
        try:
            self.redis.ping()
            return True
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f'Redis connection lost: {e}. Attempting to reconnect...')
            self.redis = self._create_redis_connection()
            return False

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
            logger.error(f'Error adding key: {key} to cache: {e}')
            raise

    @_with_retry
    def get_str(self, key: str, default: Any = None) -> Optional[str]:
        try:
            value = self.redis.get(f'{self.namespace}/{key}')
            return value if value is not None else default

        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error getting key: {key} from cache: {e}')
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
            logger.error(f'Error popping key: {key} from cache: {e}')
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
            logger.error(f'Error incrementing key: {key} in cache: {e}')
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
            logger.error(f'Error removing key: {key} from cache: {e}')
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
            logger.error(f'Error publishing to channel {channel}: {e}')
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
            logger.error(f'Error appending to stream {stream}: {e}')
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
            logger.error(f'Error reading from stream group {group}: {e}')
            raise

    @_with_retry
    def xack(self, stream: str, group: str, *message_ids: str) -> int:
        """Acknowledge one or more messages in a consumer group."""
        try:
            return self.redis.xack(f'{self.namespace}/{stream}', group, *message_ids)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error acknowledging messages on stream {stream}: {e}')
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
            logger.error(f'Error listing pending entries on stream {stream}: {e}')
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
            logger.error(f'Error claiming idle entries on stream {stream}: {e}')
            raise
        # [next_start_id, claimed, deleted_ids] (Redis 7) or the first two (6.2)
        return result[1] if result and len(result) > 1 else []

    def close(self):
        try:
            self.pool.disconnect()
            if self._pubsub_pool is not None:
                self._pubsub_pool.disconnect()
            logger.info('Redis connection pool closed successfully')
        except Exception as e:
            logger.error(f'Error closing Redis connection pool: {e}')

    def _retry_with_backoff(self, func: callable, *args, **kwargs) -> Any:
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except (RedisError, ConnectionError, TimeoutError) as e:
                retries += 1
                if retries >= self.max_retries:
                    logger.error(f'Max retries reached for {func.__name__}: {e}')
                    raise
                backoff = min(
                    self.initial_backoff * (2 ** (retries - 1)), self.max_backoff
                )
                logger.warning(f'Retrying {func.__name__} in {backoff} seconds...')
                time.sleep(backoff)
