import asyncio
import contextvars
import functools
import socket
import threading
import time
import uuid
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    TypeVar,
)

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from db_repo_module.cache.lua_scripts import (
    BEGIN_CHANGE_SCRIPT,
    END_CHANGE_SCRIPT,
    PENDING_MARKER,
    PENDING_TTL_SECONDS,
    TOKEN_TTL_SECONDS,
)
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


# Attempts a caller asked for on one a* call, applied to the sync fallback too.
_attempts_override: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    'cache_attempts_override', default=None
)


def _with_retry(method: F) -> F:
    """Retry a CacheManager method with the instance's settings.

    A plain tenacity ``@retry`` is bound when the class is defined, so it could
    not read the [redis] settings. Each call gets a fresh copy of the policy,
    the same way tenacity's own decorator does.
    """

    @functools.wraps(method)
    def wrapper(self: 'BaseCache', *args: Any, **kwargs: Any) -> Any:
        policy = self._retry_policy.copy()
        attempts = _attempts_override.get()
        if attempts:
            policy = policy.copy(stop=stop_after_attempt(attempts))
        return policy(method, self, *args, **kwargs)

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


class _BoundedHandshakeMixin:
    """Bound the connection handshake on a socket that otherwise has no timeout.

    The pubsub socket waits for messages indefinitely (socket_timeout=None), and
    redis-py reads the AUTH/SELECT replies in on_connect with that same socket
    timeout. A server that accepts the TCP connection but never answers would
    hang the listener there. The handshake gets its own timeout instead, and the
    socket goes back to waiting indefinitely once it is done.
    """

    def __init__(self, *args, handshake_timeout: Optional[float] = None, **kwargs):
        self._handshake_timeout = handshake_timeout
        super().__init__(*args, **kwargs)

    def on_connect(self):
        self._sock.settimeout(self._handshake_timeout)
        try:
            super().on_connect()
        finally:
            # A failed handshake disconnects, which clears the socket.
            if self._sock is not None:
                self._sock.settimeout(self.socket_timeout)


class _PubSubConnection(_BoundedHandshakeMixin, Connection):
    pass


class _PubSubSSLConnection(_BoundedHandshakeMixin, SSLConnection):
    pass


class BaseCache(CommonCache):
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
                # No read timeout while idle, but a bounded AUTH/SELECT handshake.
                pool_kwargs['connection_class'] = (
                    _PubSubSSLConnection
                    if issubclass(pool_kwargs['connection_class'], SSLConnection)
                    else _PubSubConnection
                )
                pool_kwargs['handshake_timeout'] = self._socket_timeout
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
            # The pool was supplied from outside, so close it explicitly too.
            await client.aclose(close_connection_pool=True)

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
                # to_thread copies the context, so the thread sees the same attempts.
                token = _attempts_override.set(attempts)
                try:
                    return await asyncio.wait_for(
                        asyncio.to_thread(sync_fallback), limit
                    )
                finally:
                    _attempts_override.reset(token)

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

    def _rt_keys(self, key: str) -> tuple[str, str]:
        base = f'{self.namespace}/rt/{{{key}}}'
        return base, f'{base}:gen'

    def _rt_writers_key(self, key: str) -> str:
        return f'{self.namespace}/rt/{{{key}}}:w'

    @staticmethod
    def _new_token() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _as_str(value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        return value.decode('utf-8')

    @_with_retry
    def _call_sync(self, fn: Callable[[], T]) -> T:
        """Run a sync Redis callable under the instance's retry policy, like the
        decorated sync methods the other fallbacks use."""
        return fn()

    async def _rotate(
        self, keys: tuple[str, ...], *, pending: bool, writer: str
    ) -> None:
        """Begin (``pending=True``) or end a change for every key, in one round
        trip. Raises on failure.

        Begin registers a writer and sets a pending marker; end deregisters it,
        and the last writer out sets a fresh token. Both drop the cached value
        and the plain ``get_str``/``add`` key of the same name, so code (or old
        workers mid-deploy) still using the plain API never keeps serving a
        value this change made stale.
        """
        if pending:
            script, ttl, prefix = (
                BEGIN_CHANGE_SCRIPT,
                PENDING_TTL_SECONDS,
                PENDING_MARKER,
            )
        else:
            script, ttl, prefix = END_CHANGE_SCRIPT, TOKEN_TTL_SECONDS, ''

        def queue(pipe: Any) -> Any:
            # A new token on every attempt: a retried rotation never brings
            # back a token that fills may already carry.
            token = prefix + self._new_token()
            for key in keys:
                value_key, gen_key = self._rt_keys(key)
                pipe.eval(
                    script,
                    3,
                    value_key,
                    gen_key,
                    self._rt_writers_key(key),
                    token,
                    ttl,
                    writer,
                )
                pipe.delete(f'{self.namespace}/{key}')
            return pipe

        async def rotate(client: aioredis.Redis) -> Any:
            return await queue(client.pipeline(transaction=False)).execute()

        def rotate_sync() -> Any:
            return self._call_sync(
                lambda: queue(self.redis.pipeline(transaction=False)).execute()
            )

        await self._run_async('ROTATE', rotate, rotate_sync, None, None)

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
