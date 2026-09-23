from typing import Any

from db_repo_module.cache.application_cache import KNOWLEDGE_BASES_CACHE_KEY
from db_repo_module.models.knowledge_bases import KnowledgeBase
from floware.repositories.base_cached_repository import BaseCachedRepository


class AppKnowledgeBaseRepository(BaseCachedRepository[KnowledgeBase]):
    async def get_all(self) -> list[dict[str, Any]]:
        cached = self._read_cache(KNOWLEDGE_BASES_CACHE_KEY)
        if cached is not None:
            return cached

        knowledge_bases = await self.repository.find()
        payload = [knowledge_base.to_dict() for knowledge_base in knowledge_bases]
        self._write_cache(KNOWLEDGE_BASES_CACHE_KEY, payload)
        return payload
