import json
from typing import List, Optional
from uuid import UUID

from common_module.call_processing_cache import CallProcessingCacheInvalidator
from common_module.log.logger import logger
from common_module.security.secret_cipher import SecretCipher
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from voice_agents_module.utils.cache_utils import (
    get_stt_config_cache_key,
    get_stt_configs_list_cache_key,
)


class SttConfigService:
    """Service for handling STT configuration CRUD operations with caching"""

    def __init__(
        self,
        stt_config_repository: SQLAlchemyRepository[SttConfig],
        cache_manager: CacheManager,
        cache_invalidator: CallProcessingCacheInvalidator,
        secret_cipher: SecretCipher,
    ):
        """
        Initialize the STT config service

        Args:
            stt_config_repository: Repository for STT configs
            cache_manager: Cache manager instance
            cache_invalidator: Invalidates call_processing's cached configs
            secret_cipher: Protects the api_key at rest
        """
        self.stt_config_repository = stt_config_repository
        self.cache_manager = cache_manager
        self.cache_invalidator = cache_invalidator
        self.secret_cipher = secret_cipher
        self.stt_config_cache_time = 3600 * 24

    async def create_config(
        self,
        display_name: str,
        description: Optional[str] = None,
        provider: str = None,
        api_key: str = None,
        region: Optional[str] = None,
    ) -> dict:
        """
        Create a new STT configuration

        Args:
            display_name: Display name for the configuration
            description: Optional description
            provider: STT provider
            api_key: API key for the STT provider
            region: Region for the provider (e.g. Azure region)

        Returns:
            Created STT config as dict
        """
        logger.info(
            f'Creating STT config - display_name: {display_name}, provider: {provider}'
        )

        config = await self.stt_config_repository.create(
            display_name=display_name,
            description=description,
            provider=provider,
            api_key=await self.secret_cipher.aprotect(api_key),
            region=region,
        )

        # Cache the stored form (api_key is ciphertext when encryption is on)
        stored_dict = config.to_stored_dict()
        cache_key = get_stt_config_cache_key(config.id)
        self.cache_manager.add(
            cache_key, json.dumps(stored_dict), expiry=self.stt_config_cache_time
        )

        # Invalidate list cache
        list_cache_key = get_stt_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate('stt_config', config.id, 'create')

        logger.info(f'Successfully created STT config with id: {config.id}')
        return SttConfig.public_dict(stored_dict)

    async def get_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an STT configuration by ID, without the api_key (has_api_key instead)

        Args:
            config_id: UUID of the configuration

        Returns:
            STT config as dict or None if not found
        """
        stored_dict = await self.get_stored_config(config_id)
        return SttConfig.public_dict(stored_dict) if stored_dict else None

    async def get_runtime_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an STT configuration with the plaintext api_key, for making provider calls.
        The result is never cached.
        """
        stored_dict = await self.get_stored_config(config_id)
        if not stored_dict:
            return None
        return {
            **stored_dict,
            'api_key': await self.secret_cipher.areveal(stored_dict.get('api_key')),
        }

    async def get_stored_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an STT configuration as stored (with caching): the api_key is
        ciphertext when encryption is on, plaintext otherwise.

        Args:
            config_id: UUID of the configuration

        Returns:
            STT config as dict or None if not found
        """
        cache_key = get_stt_config_cache_key(config_id)

        # Try cache first
        cached_config_str = self.cache_manager.get_str(cache_key)
        if cached_config_str:
            logger.info(f'Cache hit for STT config: {config_id}')
            return json.loads(cached_config_str)

        # Cache miss - fetch from DB
        logger.info(f'Cache miss - fetching STT config from DB: {config_id}')
        config = await self.stt_config_repository.find_one(
            id=config_id, is_deleted=False
        )

        if config:
            # Convert to dict and cache
            config_dict = config.to_stored_dict()
            self.cache_manager.add(
                cache_key, json.dumps(config_dict), expiry=self.stt_config_cache_time
            )
            return config_dict

        return None

    async def list_configs(self) -> List[dict]:
        """
        List all STT configurations (with caching), without their api_keys

        Returns:
            List of STT configs as dicts
        """
        list_cache_key = get_stt_configs_list_cache_key()

        # Try cache first
        cached_list_str = self.cache_manager.get_str(list_cache_key)
        if cached_list_str:
            logger.info('Cache hit for STT configs list')
            return [SttConfig.public_dict(c) for c in json.loads(cached_list_str)]

        # Cache miss - fetch from DB
        logger.info('Cache miss - fetching STT configs list from DB')
        configs = await self.stt_config_repository.find(is_deleted=False)

        # Cache the stored form, return the public form
        configs_dicts = [config.to_stored_dict() for config in configs]
        self.cache_manager.add(
            list_cache_key, json.dumps(configs_dicts), expiry=self.stt_config_cache_time
        )

        return [SttConfig.public_dict(c) for c in configs_dicts]

    async def update_config(self, config_id: UUID, **update_data) -> Optional[dict]:
        """
        Update an STT configuration

        Args:
            config_id: UUID of the configuration
            **update_data: Fields to update

        Returns:
            Updated config as dict or None if not found
        """
        logger.info(f'Updating STT config: {config_id}')

        existing_config = await self.stt_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return None

        if 'api_key' in update_data:
            update_data['api_key'] = await self.secret_cipher.aprotect(
                update_data['api_key']
            )

        updated_config = await self.stt_config_repository.find_one_and_update(
            {'id': config_id}, refresh=True, **update_data
        )

        # Invalidate caches
        cache_key = get_stt_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_stt_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate('stt_config', config_id, 'update')

        logger.info(f'Successfully updated STT config: {config_id}')
        return updated_config.to_dict()

    async def delete_config(self, config_id: UUID) -> bool:
        """
        Delete an STT configuration (soft delete)

        Args:
            config_id: UUID of the configuration

        Returns:
            True if deleted, False if not found
        """
        logger.info(f'Deleting STT config: {config_id}')

        existing_config = await self.stt_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return False

        await self.stt_config_repository.find_one_and_update(
            {'id': config_id}, is_deleted=True
        )

        # Invalidate caches
        cache_key = get_stt_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_stt_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate('stt_config', config_id, 'delete')

        logger.info(f'Successfully deleted STT config: {config_id}')
        return True
