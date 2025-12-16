import json
from typing import List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from llm_inference_config_module.utils.cache_utils import (
    get_llm_inference_config_cache_key,
    get_llm_inference_configs_list_cache_key,
)
from llm_inference_config_module.utils.cache_invalidation import (
    invalidate_call_processing_cache,
)


class LlmInferenceConfigService:
    """Service for handling LLM inference configuration CRUD operations with caching"""

    def __init__(
        self,
        llm_inference_config_repository: SQLAlchemyRepository[LlmInferenceConfig],
        cache_manager: CacheManager,
    ):
        """
        Initialize the LLM inference config service

        Args:
            llm_inference_config_repository: Repository for LLM inference configs
            cache_manager: Cache manager instance
        """
        self.llm_inference_config_repository = llm_inference_config_repository
        self.cache_manager = cache_manager
        self.llm_inference_config_cache_time = 3600 * 24

    async def create_config(
        self,
        llm_model: str,
        display_name: str,
        api_key: str,
        type: str,
        base_url: Optional[str] = None,
        parameters: Optional[dict] = None,
        model_type: Optional[str] = 'llm',
    ) -> dict:
        """
        Create a new LLM inference configuration

        Args:
            llm_model: LLM model name
            display_name: Display name for the config
            api_key: API key for the LLM provider
            type: Type of inference engine
            base_url: Base URL for the LLM provider (optional)
            parameters: LLM parameters like temperature, max_tokens, etc. (optional)
            model_type: Type of model: "llm" or "embedding" (defaults to "llm")

        Returns:
            Created LLM inference config as dict
        """
        logger.info(
            f'Creating LLM inference config - model: {llm_model}, type: {type}, model_type: {model_type}'
        )

        config = await self.llm_inference_config_repository.create(
            llm_model=llm_model,
            display_name=display_name,
            api_key=api_key,
            type=type,
            base_url=base_url,
            parameters=parameters,
            model_type=model_type,
        )

        # Convert to dict
        config_dict = config.to_dict(exclude_api_key=False)

        # Cache the config
        cache_key = get_llm_inference_config_cache_key(config.id)
        self.cache_manager.add(
            cache_key,
            json.dumps(config_dict),
            expiry=self.llm_inference_config_cache_time,
        )

        # Invalidate list cache
        list_cache_key = get_llm_inference_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache(
            'llm_inference_config', config.id, 'create'
        )

        logger.info(f'Successfully created LLM inference config with id: {config.id}')
        return config_dict

    async def get_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an LLM inference configuration by ID (with caching)

        Args:
            config_id: UUID of the configuration

        Returns:
            LLM inference config as dict or None if not found
        """
        cache_key = get_llm_inference_config_cache_key(config_id)

        # Try cache first
        cached_config_str = self.cache_manager.get_str(cache_key)
        if cached_config_str:
            logger.info(f'Cache hit for LLM inference config: {config_id}')
            return json.loads(cached_config_str)

        # Cache miss - fetch from DB
        logger.info(f'Cache miss - fetching LLM inference config from DB: {config_id}')
        config = await self.llm_inference_config_repository.find_one(
            id=config_id, is_deleted=False
        )

        if config:
            # Convert to dict and cache
            config_dict = config.to_dict(exclude_api_key=False)
            self.cache_manager.add(
                cache_key,
                json.dumps(config_dict),
                expiry=self.llm_inference_config_cache_time,
            )
            return config_dict

        return None

    async def list_configs(self) -> List[dict]:
        """
        List all LLM inference configurations (with caching)

        Returns:
            List of LLM inference configs as dicts
        """
        list_cache_key = get_llm_inference_configs_list_cache_key()

        # Try cache first
        cached_list_str = self.cache_manager.get_str(list_cache_key)
        if cached_list_str:
            logger.info('Cache hit for LLM inference configs list')
            return json.loads(cached_list_str)

        # Cache miss - fetch from DB
        logger.info('Cache miss - fetching LLM inference configs list from DB')
        configs = await self.llm_inference_config_repository.find(is_deleted=False)

        # Convert to dicts and cache
        configs_dicts = [config.to_dict(exclude_api_key=False) for config in configs]
        self.cache_manager.add(
            list_cache_key,
            json.dumps(configs_dicts),
            expiry=self.llm_inference_config_cache_time,
        )

        return configs_dicts

    async def update_config(self, config_id: UUID, **update_data) -> Optional[dict]:
        """
        Update an LLM inference configuration

        Args:
            config_id: UUID of the configuration
            **update_data: Fields to update

        Returns:
            Updated config as dict or None if not found
        """
        logger.info(f'Updating LLM inference config: {config_id}')

        existing_config = await self.llm_inference_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return None

        updated_config = await self.llm_inference_config_repository.find_one_and_update(
            {'id': config_id}, refresh=True, **update_data
        )

        # Invalidate caches
        cache_key = get_llm_inference_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_llm_inference_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache(
            'llm_inference_config', config_id, 'update'
        )

        logger.info(f'Successfully updated LLM inference config: {config_id}')
        return updated_config.to_dict(exclude_api_key=False)

    async def delete_config(self, config_id: UUID) -> bool:
        """
        Delete an LLM inference configuration (soft delete)

        Args:
            config_id: UUID of the configuration

        Returns:
            True if deleted, False if not found
        """
        logger.info(f'Deleting LLM inference config: {config_id}')

        existing_config = await self.llm_inference_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return False

        await self.llm_inference_config_repository.find_one_and_update(
            {'id': config_id}, is_deleted=True
        )

        # Invalidate caches
        cache_key = get_llm_inference_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_llm_inference_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache(
            'llm_inference_config', config_id, 'delete'
        )

        logger.info(f'Successfully deleted LLM inference config: {config_id}')
        return True
