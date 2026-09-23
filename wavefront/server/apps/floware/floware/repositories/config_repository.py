from typing import Any, Optional

from db_repo_module.cache.application_cache import (
    APP_CONFIG_CACHE_KEY,
    invalidate_app_config_cache,
)
from db_repo_module.models.config import Config
from floware.repositories.base_cached_repository import BaseCachedRepository


class AppConfigRepository(BaseCachedRepository[Config]):
    async def get(self) -> Optional[dict[str, Any]]:
        cached = self._read_cache(APP_CONFIG_CACHE_KEY)
        if cached is not None:
            return cached

        config_records = await self.repository.find(key='app_config')
        if not config_records:
            return None

        value = config_records[0].value or {}
        self._write_cache(APP_CONFIG_CACHE_KEY, value)
        return value

    async def upsert(self, value: dict[str, Any]) -> None:
        await self.repository.upsert(
            filters={'key': 'app_config'},
            value=value,
        )
        invalidate_app_config_cache(self.cache_manager)
