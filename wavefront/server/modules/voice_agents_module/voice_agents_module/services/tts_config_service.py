import json
from typing import List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.tts_config import TtsConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from voice_agents_module.utils.cache_utils import (
    get_tts_config_cache_key,
    get_tts_configs_list_cache_key,
)
from voice_agents_module.utils.cache_invalidation import (
    invalidate_call_processing_cache,
)


class TtsConfigService:
    """Service for handling TTS configuration CRUD operations with caching"""

    def __init__(
        self,
        tts_config_repository: SQLAlchemyRepository[TtsConfig],
        cache_manager: CacheManager,
    ):
        """
        Initialize the TTS config service

        Args:
            tts_config_repository: Repository for TTS configs
            cache_manager: Cache manager instance
        """
        self.tts_config_repository = tts_config_repository
        self.cache_manager = cache_manager
        self.tts_config_cache_time = 3600 * 24

    async def create_config(
        self,
        display_name: str,
        description: Optional[str] = None,
        provider: str = None,
        api_key: str = None,
    ) -> dict:
        """
        Create a new TTS configuration

        Args:
            display_name: Display name for the configuration
            description: Optional description
            provider: TTS provider
            api_key: API key for the TTS provider

        Returns:
            Created TTS config as dict
        """
        logger.info(
            f'Creating TTS config - display_name: {display_name}, provider: {provider}'
        )

        config = await self.tts_config_repository.create(
            display_name=display_name,
            description=description,
            provider=provider,
            api_key=api_key,
        )

        # Convert to dict
        config_dict = config.to_dict(exclude_api_key=False)

        # Cache the config
        cache_key = get_tts_config_cache_key(config.id)
        self.cache_manager.add(
            cache_key, json.dumps(config_dict), expiry=self.tts_config_cache_time
        )

        # Invalidate list cache
        list_cache_key = get_tts_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('tts_config', config.id, 'create')

        logger.info(f'Successfully created TTS config with id: {config.id}')
        return config_dict

    async def get_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get a TTS configuration by ID (with caching)

        Args:
            config_id: UUID of the configuration

        Returns:
            TTS config as dict or None if not found
        """
        cache_key = get_tts_config_cache_key(config_id)

        # Try cache first
        cached_config_str = self.cache_manager.get_str(cache_key)
        if cached_config_str:
            logger.info(f'Cache hit for TTS config: {config_id}')
            return json.loads(cached_config_str)

        # Cache miss - fetch from DB
        logger.info(f'Cache miss - fetching TTS config from DB: {config_id}')
        config = await self.tts_config_repository.find_one(
            id=config_id, is_deleted=False
        )

        if config:
            # Convert to dict and cache
            config_dict = config.to_dict(exclude_api_key=False)
            self.cache_manager.add(
                cache_key, json.dumps(config_dict), expiry=self.tts_config_cache_time
            )
            return config_dict

        return None

    async def list_configs(self) -> List[dict]:
        """
        List all TTS configurations (with caching)

        Returns:
            List of TTS configs as dicts
        """
        list_cache_key = get_tts_configs_list_cache_key()

        # Try cache first
        cached_list_str = self.cache_manager.get_str(list_cache_key)
        if cached_list_str:
            logger.info('Cache hit for TTS configs list')
            return json.loads(cached_list_str)

        # Cache miss - fetch from DB
        logger.info('Cache miss - fetching TTS configs list from DB')
        configs = await self.tts_config_repository.find(is_deleted=False)

        # Convert to dicts and cache
        configs_dicts = [config.to_dict(exclude_api_key=False) for config in configs]
        self.cache_manager.add(
            list_cache_key, json.dumps(configs_dicts), expiry=self.tts_config_cache_time
        )

        return configs_dicts

    async def update_config(self, config_id: UUID, **update_data) -> Optional[dict]:
        """
        Update a TTS configuration

        Args:
            config_id: UUID of the configuration
            **update_data: Fields to update

        Returns:
            Updated config as dict or None if not found
        """
        logger.info(f'Updating TTS config: {config_id}')

        existing_config = await self.tts_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return None

        updated_config = await self.tts_config_repository.find_one_and_update(
            {'id': config_id}, refresh=True, **update_data
        )

        # Invalidate caches
        cache_key = get_tts_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_tts_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('tts_config', config_id, 'update')

        logger.info(f'Successfully updated TTS config: {config_id}')
        return updated_config.to_dict(exclude_api_key=False)

    async def delete_config(self, config_id: UUID) -> bool:
        """
        Delete a TTS configuration (soft delete)

        Args:
            config_id: UUID of the configuration

        Returns:
            True if deleted, False if not found
        """
        logger.info(f'Deleting TTS config: {config_id}')

        existing_config = await self.tts_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return False

        await self.tts_config_repository.find_one_and_update(
            {'id': config_id}, is_deleted=True
        )

        # Invalidate caches
        cache_key = get_tts_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_tts_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('tts_config', config_id, 'delete')

        logger.info(f'Successfully deleted TTS config: {config_id}')
        return True
