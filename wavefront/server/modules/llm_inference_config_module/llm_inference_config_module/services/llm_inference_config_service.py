import json
from typing import List, Optional
from uuid import UUID

from common_module.call_processing_cache import CallProcessingCacheInvalidator
from common_module.log.logger import logger
from common_module.security.secret_cipher import SECRET_MASK, SecretCipher
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from llm_inference_config_module.utils.cache_utils import (
    get_llm_inference_config_cache_key,
    get_llm_inference_configs_list_cache_key,
)


class LlmInferenceConfigService:
    """Service for handling LLM inference configuration CRUD operations with caching

    The api_key is stored (and cached) as `secret_cipher.protect` returns it, so
    ciphertext when envelope encryption is on. Only `get_runtime_config` hands
    out the plaintext, and never caches it.
    """

    def __init__(
        self,
        llm_inference_config_repository: SQLAlchemyRepository[LlmInferenceConfig],
        cache_manager: CacheManager,
        cache_invalidator: CallProcessingCacheInvalidator,
        secret_cipher: SecretCipher,
    ):
        """
        Initialize the LLM inference config service

        Args:
            llm_inference_config_repository: Repository for LLM inference configs
            cache_manager: Cache manager instance
            cache_invalidator: Invalidates call_processing's cached configs
            secret_cipher: Protects the api_key at rest and reveals it for use
        """
        self.llm_inference_config_repository = llm_inference_config_repository
        self.cache_manager = cache_manager
        self.cache_invalidator = cache_invalidator
        self.secret_cipher = secret_cipher
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
            Created LLM inference config as a public dict (no api_key)
        """
        logger.info(
            f'Creating LLM inference config - model: {llm_model}, type: {type}, model_type: {model_type}'
        )

        protected_key = await self.secret_cipher.aprotect(api_key)
        # The new row's id isn't known yet, so only the list is invalidated;
        # the config itself is filled by the first read.
        async with self.cache_manager.invalidating(
            get_llm_inference_configs_list_cache_key()
        ):
            config = await self.llm_inference_config_repository.create(
                llm_model=llm_model,
                display_name=display_name,
                api_key=protected_key,
                type=type,
                base_url=base_url,
                parameters=parameters,
                model_type=model_type,
            )

        config_dict = config.to_stored_dict()

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate(
            'llm_inference_config', config.id, 'create'
        )

        logger.info(f'Successfully created LLM inference config with id: {config.id}')
        return LlmInferenceConfig.public_dict(config_dict)

    async def get_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an LLM inference configuration by ID (with caching)

        Args:
            config_id: UUID of the configuration

        Returns:
            LLM inference config in its stored form (api_key as stored, so
            ciphertext when encryption is on) or None if not found
        """

        async def load() -> Optional[str]:
            config = await self.llm_inference_config_repository.find_one(
                id=config_id, is_deleted=False
            )
            return json.dumps(config.to_stored_dict()) if config else None

        cached = await self.cache_manager.read_through(
            get_llm_inference_config_cache_key(config_id),
            load,
            ttl=self.llm_inference_config_cache_time,
        )
        return json.loads(cached) if cached else None

    async def get_public_config(self, config_id: UUID) -> Optional[dict]:
        """Get an LLM inference configuration by ID in its public form (no api_key)"""
        config_dict = await self.get_config(config_id)
        return LlmInferenceConfig.public_dict(config_dict) if config_dict else None

    async def get_runtime_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get an LLM inference configuration with its plaintext api_key, for
        making provider calls. The result stays in memory and is never cached.

        Args:
            config_id: UUID of the configuration

        Returns:
            LLM inference config as dict or None if not found
        """
        config_dict = await self.get_config(config_id)
        if not config_dict:
            return None

        runtime_config = dict(config_dict)
        runtime_config['api_key'] = await self.secret_cipher.areveal(
            config_dict.get('api_key')
        )
        return runtime_config

    async def list_configs(self) -> List[dict]:
        """
        List all LLM inference configurations (with caching)

        Returns:
            List of LLM inference configs as public dicts (no api_key)
        """

        async def load() -> Optional[str]:
            configs = await self.llm_inference_config_repository.find(is_deleted=False)
            return json.dumps([config.to_stored_dict() for config in configs])

        cached = await self.cache_manager.read_through(
            get_llm_inference_configs_list_cache_key(),
            load,
            ttl=self.llm_inference_config_cache_time,
        )
        return [LlmInferenceConfig.public_dict(c) for c in json.loads(cached)]

    async def update_config(self, config_id: UUID, **update_data) -> Optional[dict]:
        """
        Update an LLM inference configuration

        Args:
            config_id: UUID of the configuration
            **update_data: Fields to update

        Returns:
            Updated config as a public dict (no api_key) or None if not found
        """
        logger.info(f'Updating LLM inference config: {config_id}')

        existing_config = await self.llm_inference_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return None

        # The mask means "keep the stored key"
        if update_data.get('api_key') == SECRET_MASK:
            del update_data['api_key']
        if 'api_key' in update_data:
            update_data['api_key'] = await self.secret_cipher.aprotect(
                update_data['api_key']
            )

        # Strict before the write (Redis down: 503, nothing changed), so a
        # runtime lookup can never keep using a superseded key or config.
        async with self.cache_manager.invalidating(
            get_llm_inference_config_cache_key(config_id),
            get_llm_inference_configs_list_cache_key(),
        ):
            updated_config = (
                await self.llm_inference_config_repository.find_one_and_update(
                    {'id': config_id}, refresh=True, **update_data
                )
            )

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate(
            'llm_inference_config', config_id, 'update'
        )

        logger.info(f'Successfully updated LLM inference config: {config_id}')
        return updated_config.to_dict()

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

        async with self.cache_manager.invalidating(
            get_llm_inference_config_cache_key(config_id),
            get_llm_inference_configs_list_cache_key(),
        ):
            await self.llm_inference_config_repository.find_one_and_update(
                {'id': config_id}, is_deleted=True
            )

        # Invalidate cache in call_processing
        await self.cache_invalidator.invalidate(
            'llm_inference_config', config_id, 'delete'
        )

        logger.info(f'Successfully deleted LLM inference config: {config_id}')
        return True
