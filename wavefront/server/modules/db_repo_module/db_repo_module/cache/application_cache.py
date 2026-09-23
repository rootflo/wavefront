"""Shared application cache keys for settings/config resource lists.

CacheManager is constructed with namespace=app_name, so keys are stored as
`{app_name}/{key}` in Redis. Keep these keys app-agnostic so any deployment
can share the same helpers.
"""

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager

APP_CONFIG_CACHE_KEY = 'app_config'
DATASOURCES_CACHE_KEY = 'datasources'
KNOWLEDGE_BASES_CACHE_KEY = 'knowledge_bases'
APPLICATION_CACHE_TTL_SECONDS = 60 * 60


def _invalidate(cache_manager: CacheManager, key: str, label: str) -> None:
    try:
        cache_manager.remove(key)
    except Exception as e:
        # A stale entry is recoverable via TTL; failing a write after commit is not.
        logger.warning(f'Failed to invalidate {label} cache: {e}')


def invalidate_app_config_cache(cache_manager: CacheManager) -> None:
    _invalidate(cache_manager, APP_CONFIG_CACHE_KEY, 'app config')


def invalidate_datasources_cache(cache_manager: CacheManager) -> None:
    _invalidate(cache_manager, DATASOURCES_CACHE_KEY, 'datasources')


def invalidate_knowledge_bases_cache(cache_manager: CacheManager) -> None:
    _invalidate(cache_manager, KNOWLEDGE_BASES_CACHE_KEY, 'knowledge bases')
