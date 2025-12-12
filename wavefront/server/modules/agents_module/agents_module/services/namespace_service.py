from typing import List
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

        # Try cache first
        cached_namespace = self.cache_manager.get_str(cache_key)
        if cached_namespace:
            logger.info(f'Cache hit for namespace: {name}')
            return json.loads(cached_namespace)

        # Fetch from DB
        logger.info(f'Fetching namespace from DB: {name}')
        namespace = await self.namespace_repository.find_one(name=name)

        if not namespace:
            raise ValueError(f'Namespace not found: {name}')

        namespace_dict = namespace.to_dict()

        # Cache the result
        self.cache_manager.add(
            cache_key, json.dumps(namespace_dict), expiry=self.cache_ttl
        )

        return namespace_dict

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

        # Create namespace
        logger.info(f'Creating namespace: {name}')
        namespace = Namespace(name=name)
        created_namespace = await self.namespace_repository.save(namespace)

        namespace_dict = created_namespace.to_dict()

        # Cache the new namespace
        cache_key = get_namespace_cache_key(name)
        self.cache_manager.add(
            cache_key, json.dumps(namespace_dict), expiry=self.cache_ttl
        )

        # Invalidate list cache
        list_cache_key = get_namespaces_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        logger.info(f'Successfully created namespace: {name}')
        return namespace_dict

    async def get_or_create_namespace(self, name: str) -> dict:
        """
        Get namespace if exists, otherwise create it (single DB call)

        Args:
            name: The namespace name

        Returns:
            dict: Namespace details
        """
        cache_key = get_namespace_cache_key(name)

        # Try cache first
        cached_namespace = self.cache_manager.get_str(cache_key)
        if cached_namespace:
            logger.info(f'Cache hit for namespace: {name}')
            return json.loads(cached_namespace)

        # Check DB
        namespace = await self.namespace_repository.find_one(name=name)

        if namespace:
            # Namespace exists
            namespace_dict = namespace.to_dict()
            self.cache_manager.add(
                cache_key, json.dumps(namespace_dict), expiry=self.cache_ttl
            )
            return namespace_dict
        else:
            # Create new namespace
            logger.info(f'Creating namespace: {name}')
            created_namespace = await self.namespace_repository.create(name=name)

            namespace_dict = created_namespace.to_dict()

            # Cache the new namespace
            self.cache_manager.add(
                cache_key, json.dumps(namespace_dict), expiry=self.cache_ttl
            )

            # Invalidate list cache
            list_cache_key = get_namespaces_list_cache_key()
            self.cache_manager.remove(list_cache_key)

            logger.info(f'Successfully created namespace: {name}')
            return namespace_dict

    async def list_namespaces(self) -> List[dict]:
        """
        List all namespaces with caching

        Returns:
            List[dict]: List of all namespaces
        """
        cache_key = get_namespaces_list_cache_key()

        # Try cache first
        cached_list = self.cache_manager.get_str(cache_key)
        if cached_list:
            logger.info('Cache hit for namespaces list')
            return json.loads(cached_list)

        # Fetch from DB
        logger.info('Fetching namespaces list from DB')
        namespaces = await self.namespace_repository.find()

        namespaces_list = [ns.to_dict() for ns in namespaces]

        # Cache the result
        self.cache_manager.add(
            cache_key, json.dumps(namespaces_list), expiry=self.cache_ttl
        )

        logger.info(f'Successfully retrieved {len(namespaces_list)} namespaces')
        return namespaces_list
