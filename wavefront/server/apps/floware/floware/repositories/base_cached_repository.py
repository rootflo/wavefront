import json
from typing import Any, Generic, Optional, TypeVar

from common_module.log.logger import logger
from db_repo_module.cache.application_cache import APPLICATION_CACHE_TTL_SECONDS
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

T = TypeVar('T')


class BaseCachedRepository(Generic[T]):
    """Shared Redis cache helpers for application repositories."""

    def __init__(
        self,
        repository: SQLAlchemyRepository[T],
        cache_manager: CacheManager,
    ) -> None:
        self.repository = repository
        self.cache_manager = cache_manager

    def _read_cache(self, key: str) -> Optional[Any]:
        try:
            cached = self.cache_manager.get_str(key)
            if cached is not None:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f'Cache read failed for {key}: {e}')
        return None

    def _write_cache(self, key: str, value: Any) -> None:
        try:
            self.cache_manager.add(
                key,
                json.dumps(value),
                expiry=APPLICATION_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f'Cache write failed for {key}: {e}')
