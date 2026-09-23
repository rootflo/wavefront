from typing import Any

from db_repo_module.cache.application_cache import DATASOURCES_CACHE_KEY
from db_repo_module.models.datasource import Datasource
from floware.repositories.base_cached_repository import BaseCachedRepository


class AppDatasourceRepository(BaseCachedRepository[Datasource]):
    async def get_all(self) -> list[dict[str, Any]]:
        cached = self._read_cache(DATASOURCES_CACHE_KEY)
        if cached is not None:
            return cached

        datasources = await self.repository.find()
        payload = [
            datasource.to_dict(exclude_config=True) for datasource in datasources
        ]
        self._write_cache(DATASOURCES_CACHE_KEY, payload)
        return payload
