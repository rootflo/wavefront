import asyncio
import json
import time
from typing import Any, Dict, Optional, Union

from call_processing.log.logger import logger

from redis import Connection
from redis import ConnectionError
from redis import BlockingConnectionPool
from redis import ConnectionPool
from redis import Redis
from redis import RedisError
from redis import SSLConnection
from redis import TimeoutError
from redis.exceptions import OutOfMemoryError
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential


def _is_retryable_redis_error(exc: BaseException) -> bool:
    """Retry everything except OOM, which fails the same way every time."""
    if isinstance(exc, OutOfMemoryError):
        return False
    return isinstance(exc, (RedisError, ConnectionError, TimeoutError))


# Consume the join token: validate, flip pending -> joined, drop the token hash.
# Runs atomically so two concurrent offers cannot both win.
#
# KEYS[1] room key
# ARGV[1] token hash, ARGV[2] voice_agent_id, ARGV[3] joined_at, ARGV[4] joined TTL
# Returns {'ok'} or {'err', <code>}
_CONSUME_ROOM_JOIN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return {'err', 'room_expired'}
end
local room = cjson.decode(raw)
if room['status'] == 'ended' then
    return {'err', 'room_expired'}
end
if room['status'] ~= 'pending' then
    return {'err', 'room_already_joined'}
end
if room['voice_agent_id'] ~= ARGV[2] then
    return {'err', 'invalid_join_token'}
end
if (not room['join_token_hash']) or room['join_token_hash'] ~= ARGV[1] then
    return {'err', 'invalid_join_token'}
end
room['status'] = 'joined'
room['joined_at'] = ARGV[3]
room['join_token_hash'] = nil
redis.call('SET', KEYS[1], cjson.encode(room), 'EX', tonumber(ARGV[4]))
return {'ok'}
"""

# Attach pc_id / instance_id to a joined room, keeping its TTL.
# ARGV[1] pc_id, ARGV[2] instance_id
_ATTACH_ROOM_CONNECTION_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return 0
end
local room = cjson.decode(raw)
room['pc_id'] = ARGV[1]
room['instance_id'] = ARGV[2]
redis.call('SET', KEYS[1], cjson.encode(room), 'KEEPTTL')
return 1
"""

# Record a completed agent swap, keeping the room TTL. Refuses agents that are not
# on the room's allowlist, so the record can never point outside it.
# ARGV[1] agent_id
# Returns {'ok', <swap_count>} or {'err', <code>}
_RECORD_ROOM_SWAP_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return {'err', 'room_expired'}
end
local room = cjson.decode(raw)
if room['status'] ~= 'joined' then
    return {'err', 'room_expired'}
end
local allowed = false
if type(room['allowed_agent_ids']) == 'table' then
    for _, id in ipairs(room['allowed_agent_ids']) do
        if id == ARGV[1] then
            allowed = true
        end
    end
end
if not allowed then
    return {'err', 'agent_not_allowed'}
end
room['active_voice_agent_id'] = ARGV[1]
room['swap_count'] = (tonumber(room['swap_count']) or 0) + 1
redis.call('SET', KEYS[1], cjson.encode(room), 'KEEPTTL')
return {'ok', room['swap_count']}
"""


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
        # config.ini values arrive as strings
        pool_size = int(pool_size) if pool_size is not None else 10
        self.namespace = namespace
        self.redis_host = redis_host
        self.redis_port = int(redis_port)
        self.redis_protocol = redis_protocol
        self.redis_password = redis_password or None
        self.redis_db = int(redis_db)
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

            if password:
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
        retry=retry_if_exception(_is_retryable_redis_error),
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
        retry=retry_if_exception(_is_retryable_redis_error),
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

    async def aget_json(self, key: str) -> Optional[Dict]:
        """Async wrapper so Redis I/O does not block the event loop."""
        return await asyncio.to_thread(self.get_json, key)

    async def aget_str(self, key: str, default: Any = None) -> Optional[str]:
        """Async wrapper for ``get_str``."""
        return await asyncio.to_thread(self.get_str, key, default)

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

    async def aset_json(self, key: str, value: Dict, expiry: int = 3600) -> bool:
        """Async wrapper for ``set_json``."""
        return await asyncio.to_thread(self.set_json, key, value, expiry)

    def remove(self, key: str) -> bool:
        try:
            return bool(self.redis.delete(f'{self.namespace}/{key}'))
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error getting key: {key} from cache: {e}')
            raise

    def _eval_fixed_script(self, script: str, key: str, args: list[Any]) -> Any:
        """Run one of this module's fixed Lua scripts on a single namespaced key.

        Private on purpose: callers pick a script via a specific method below and
        never supply script text.
        """
        namespaced = f'{self.namespace}/{key}'
        try:
            return self.redis.eval(script, 1, namespaced, *args)
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error(f'Error running script on key {key}: {e}')
            raise

    def consume_room_join_token(
        self,
        key: str,
        token_hash: str,
        voice_agent_id: str,
        joined_at: str,
        joined_ttl_secs: int,
    ) -> Any:
        """Atomically validate a room's join token and flip it pending -> joined."""
        return self._eval_fixed_script(
            _CONSUME_ROOM_JOIN_SCRIPT,
            key,
            [token_hash, voice_agent_id, joined_at, joined_ttl_secs],
        )

    def attach_room_connection(self, key: str, pc_id: str, instance_id: str) -> Any:
        """Attach pc_id / instance_id to a room record, keeping its TTL."""
        return self._eval_fixed_script(
            _ATTACH_ROOM_CONNECTION_SCRIPT, key, [pc_id, instance_id]
        )

    def record_room_swap(self, key: str, agent_id: str) -> Any:
        """Atomically record an agent swap if the agent is on the room's allowlist."""
        return self._eval_fixed_script(_RECORD_ROOM_SWAP_SCRIPT, key, [agent_id])

    _INVALIDATE_BATCH = 500

    def invalidate_query(self, pattern: str) -> int:
        """Remove all keys matching the given pattern (SCAN, not KEYS)."""
        try:
            search_pattern = f'{self.namespace}/{pattern}'
            deleted = 0
            batch: list = []
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
