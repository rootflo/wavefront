import json
import time
from typing import Any, Dict, Optional, Union

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential
from call_processing.log.logger import logger

from redis import Connection
from redis import ConnectionError
from redis import BlockingConnectionPool
from redis import ConnectionPool
from redis import Redis
from redis import RedisError
from redis import SSLConnection
from redis import TimeoutError
from redis.credentials import CredentialProvider
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential


class AzureManagedRedisProvider(CredentialProvider):
    """
    Adapter to bridge Azure Identity with Redis CredentialProvider.
    Azure Managed Redis requires 'default' as the username and the
    Entra ID access token as the password.
    """

    def __init__(self, username: str = 'default'):
        self.credential = DefaultAzureCredential()
        self.scope = 'https://redis.azure.com/.default'
        self.username = username

    def get_credentials(self):
        try:
            token = self.credential.get_token(self.scope)
            return (self.username, token.token)
        except ClientAuthenticationError as e:
            logger.error(f'Azure authentication failed: {e}')
            raise


class CacheManager:
    def __init__(
        self,
        namespace: str = '',
        max_retries: int = 3,
        initial_backoff: int = 1,
        max_backoff: int = 10,
        connection_timeout: int = 60,
        socket_timeout: int = 60,
        socket_keepalive: bool = True,
        pool_size: Optional[int] = None,
        *,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        redis_protocol: str = 'redis',
        redis_password: str | None = None,
        redis_db: int = 0,
        redis_username: str = 'default',
        cloud_provider: str = '',
        pool_timeout: float = 2.0,
    ):
        """
        Args:
            pool_size: Max Redis connections this process may open. Defaults to
                REDIS_POOL_SIZE (10). Connections are opened on demand, so the
                cap only costs anything under concurrency. When all are in use,
                a caller waits up to REDIS_POOL_TIMEOUT (2s) for one to be
                released, then gets ConnectionError('No connection available.').
        """
        if pool_size is None:
            pool_size = 10
        self.namespace = namespace
        self.redis_host = redis_host
        self.redis_port = int(redis_port)
        self.redis_protocol = redis_protocol
        self.redis_password = redis_password or None
        self.redis_db = int(redis_db)
        self.redis_username = redis_username
        self.cloud_provider = (cloud_provider or '').lower()
        self.pool_timeout = float(pool_timeout)
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
        logger.info('Connected to Redis with connection pooling enabled')

    def _create_connection_pool(
        self,
        connection_timeout: int,
        socket_timeout: int,
        socket_keepalive: bool,
        pool_size: int,
    ) -> ConnectionPool:
        try:
            host = self.redis_host
            port = self.redis_port
            protocol = self.redis_protocol
            password = self.redis_password
            cloud_provider = self.cloud_provider

            connection_class = Connection
            if protocol == 'rediss' or port == 10000:
                logger.info(f'Using SSLConnection for Redis (Port: {port})')
                connection_class = SSLConnection

            pool_kwargs = {
                'connection_class': connection_class,
                'host': host,
                'port': port,
                'db': self.redis_db,
                'max_connections': pool_size,
                'socket_timeout': socket_timeout,
                'socket_keepalive': socket_keepalive,
                'socket_connect_timeout': connection_timeout,
                'retry_on_timeout': True,
                'health_check_interval': 30,
                'encoding': 'utf-8',
                'decode_responses': True,
            }

            if cloud_provider == 'azure' and not password:
                logger.info(
                    'Configuring Azure Entra ID (Workload Identity) authentication'
                )
                pool_kwargs['credential_provider'] = AzureManagedRedisProvider(
                    username=self.redis_username
                )
            elif password:
                pool_kwargs['password'] = password

            # Blocking: when every connection is busy, wait briefly for one to
            # be released instead of failing at once with 'Too many connections'.
            return BlockingConnectionPool(timeout=self.pool_timeout, **pool_kwargs)
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

    def get_json(self, key: str) -> Optional[Dict]:
        """
        Get JSON value from cache

        Args:
            key: Cache key

        Returns:
            Parsed JSON dict or None if key not found
        """
        try:
            value = self.get_str(key)
            if value is not None:
                return json.loads(value)
            return None
        except json.JSONDecodeError as e:
            logger.error(f'Error decoding JSON for key: {key}: {e}')
            return None

    def set_json(self, key: str, value: Dict, expiry: int = 3600) -> bool:
        """
        Set JSON value in cache

        Args:
            key: Cache key
            value: Dict to store as JSON
            expiry: TTL in seconds (default 1 hour)

        Returns:
            True if successful
        """
        try:
            json_str = json.dumps(value)
            return self.add(key, json_str, expiry=expiry)
        except (TypeError, ValueError) as e:
            logger.error(f'Error encoding JSON for key: {key}: {e}')
            return False

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
