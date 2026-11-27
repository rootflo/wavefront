from typing import Optional, List
import json

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.namespace import Namespace
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from common_module.log.logger import logger
from agents_module.utils.cache_utils import (
    get_namespace_cache_key,
    get_namespaces_list_cache_key,
)


class NamespaceService:
    """Service for handling namespace operations with caching"""

    def __init__(
        self,
        namespace_repository: SQLAlchemyRepository[Namespace],
        cache_manager: CacheManager,
    ):
        self.namespace_repository = namespace_repository
        self.cache_manager = cache_manager
        self.cache_ttl = 7200  # 2 hours for namespaces (they change less frequently)

    async def get_namespace(self, name: str) -> dict:
        """
        Get namespace by name with caching

        Args:
            name: The namespace name

        Returns:
            dict: Namespace details

        Raises:
            ValueError: If namespace not found
        """
        cache_key = get_namespace_cache_key(name)

        async def load() -> Optional[str]:
            namespace = await self.namespace_repository.find_one(name=name)
            return json.dumps(namespace.to_dict()) if namespace else None

        cached = await self.cache_manager.read_through(
            cache_key, load, ttl=self.cache_ttl
        )
        if cached is None:
            raise ValueError(f'Namespace not found: {name}')
        return json.loads(cached)

    async def create_namespace(self, name: str) -> dict:
        """
        Create a new namespace

        Args:
            name: The namespace name

        Returns:
            dict: Created namespace details

        Raises:
            ValueError: If namespace already exists
        """
        # Check if namespace already exists
        existing = await self.namespace_repository.find_one(name=name)
        if existing:
            logger.warning(f'Namespace already exists: {name}')
            raise ValueError(f'Namespace already exists: {name}')

        logger.info(f'Creating namespace: {name}')
        async with self.cache_manager.invalidating(
            get_namespace_cache_key(name), get_namespaces_list_cache_key()
        ):
            created_namespace = await self.namespace_repository.save(
                Namespace(name=name)
            )

        logger.info(f'Successfully created namespace: {name}')
        return created_namespace.to_dict()

    async def get_or_create_namespace(self, name: str) -> dict:
        """
        Get namespace if exists, otherwise create it (single DB call)

        Args:
            name: The namespace name

        Returns:
            dict: Namespace details
        """
        try:
            return await self.get_namespace(name)
        except ValueError:
            pass

        logger.info(f'Creating namespace: {name}')
        async with self.cache_manager.invalidating(
            get_namespace_cache_key(name), get_namespaces_list_cache_key()
        ):
            created_namespace = await self.namespace_repository.create(name=name)

        logger.info(f'Successfully created namespace: {name}')
        return created_namespace.to_dict()

    async def list_namespaces(self) -> List[dict]:
        """
        List all namespaces with caching

        Returns:
            List[dict]: List of all namespaces
        """

        async def load() -> Optional[str]:
            namespaces = await self.namespace_repository.find()
            return json.dumps([ns.to_dict() for ns in namespaces])

        cached = await self.cache_manager.read_through(
            get_namespaces_list_cache_key(), load, ttl=self.cache_ttl
        )
        namespaces_list = json.loads(cached)
        logger.info(f'Retrieved {len(namespaces_list)} namespaces')
        return namespaces_list
