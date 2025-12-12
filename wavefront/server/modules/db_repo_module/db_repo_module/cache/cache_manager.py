import os
import time
from typing import Any, List, Optional, Union

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from redis import ConnectionError
from redis import ConnectionPool
from redis import Redis
from redis import RedisError
from redis import TimeoutError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential


class CacheManager(CommonCache):
    def __init__(
        self,
        namespace: str = '',
        max_retries: int = 3,
        initial_backoff: int = 1,
        max_backoff: int = 10,
        connection_timeout: int = 60,
        socket_timeout: int = 60,
        socket_keepalive: bool = True,
        pool_size: int = 5,
    ):
        self.namespace = namespace
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

        self.pool = self._create_connection_pool(
            connection_timeout=connection_timeout,
            socket_timeout=socket_timeout,
            socket_keepalive=socket_keepalive,
            pool_size=pool_size,
        )

        self.redis = self._create_redis_connection()

        # Test the connection immediately - fail fast if Redis is unreachable
        try:
            self.redis.ping()
            logger.info('Connected to Redis with redis ping')
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.error(f'Failed to connect to Redis during initialization: {e}')
            logger.error('Server will not start without Redis connectivity')
            raise RuntimeError(f'Redis connection test failed: {e}') from e

    def _create_connection_pool(
        self,
        connection_timeout: int,
        socket_timeout: int,
        socket_keepalive: bool,
        pool_size: int,
    ) -> ConnectionPool:
        try:
            return ConnectionPool(
                host=str(os.getenv('REDIS_HOST', 'localhost')),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                max_connections=pool_size,
                socket_timeout=socket_timeout,
                socket_keepalive=socket_keepalive,
                socket_connect_timeout=connection_timeout,
                retry_on_timeout=True,
                health_check_interval=30,
                encoding='utf-8',
                decode_responses=True,
            )
        except Exception as e:
            logger.error(f'Failed to create connection pool: {e}s')
            raise

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RedisError, ConnectionError, TimeoutError)),
    )
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RedisError, ConnectionError, TimeoutError)),
    )
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

    def remove(self, key: str) -> bool:
        try:
            return bool(self.redis.delete(f'{self.namespace}/{key}'))
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error getting key: {key} from cache: {e}')
            raise

    def invalidate_query(self, pattern: str) -> int:
        """Remove all keys matching the given pattern"""
        try:
            # Get all keys matching the pattern
            search_pattern = f'{self.namespace}/{pattern}'
            keys = self.redis.keys(search_pattern)
            if keys:
                logger.info(
                    f'Invalidating {len(keys)} cache keys matching pattern: {pattern}'
                )
                return self.redis.delete(*keys)
            logger.info(f'No cache keys found matching pattern: {pattern}')
            return 0
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error removing keys with pattern: {pattern} from cache: {e}')
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RedisError, ConnectionError, TimeoutError)),
    )
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
            pubsub = self.redis.pubsub()

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

    def close(self):
        try:
            self.pool.disconnect()
            logger.info('Redis connection pool closed successfully')
        except Exception as e:
            logger.error(f'Error closing Redis connection pool: {e}')

    def _retry_with_backoff(self, func: callable, *args, **kwargs) -> Any:
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except (RedisError, ConnectionPool, TimeoutError) as e:
                retries += 1
                if retries >= self.max_retries:
                    logger.error(f'Max retries reached for {func.__name__}: {e}')
                    raise
                backoff = min(
                    self.initial_backoff * (2 ** (retries - 1)), self.max_backoff
                )
                logger.warning(f'Retrying {func.__name__} in {backoff} seconds...')
                time.sleep(backoff)
