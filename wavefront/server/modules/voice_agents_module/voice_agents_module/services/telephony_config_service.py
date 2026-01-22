import json
from typing import List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from voice_agents_module.models.telephony_schemas import WebhookConfig, SipConfig
from voice_agents_module.utils.cache_utils import (
    get_telephony_config_cache_key,
    get_telephony_configs_list_cache_key,
)
from voice_agents_module.utils.cache_invalidation import (
    invalidate_call_processing_cache,
)


class TelephonyConfigService:
    """Service for handling telephony configuration CRUD operations with caching"""

    def __init__(
        self,
        telephony_config_repository: SQLAlchemyRepository[TelephonyConfig],
        cache_manager: CacheManager,
    ):
        """
        Initialize the telephony config service

        Args:
            telephony_config_repository: Repository for telephony configs
            cache_manager: Cache manager instance
        """
        self.telephony_config_repository = telephony_config_repository
        self.cache_manager = cache_manager
        self.telephony_config_cache_time = 3600 * 24

    async def create_config(
        self,
        display_name: str,
        description: Optional[str] = None,
        provider: str = None,
        connection_type: str = None,
        credentials: dict = None,
        webhook_config: Optional[WebhookConfig] = None,
        sip_config: Optional[SipConfig] = None,
    ) -> dict:
        """
        Create a new telephony configuration

        Args:
            display_name: Display name for the configuration
            description: Optional description
            provider: Telephony provider
            connection_type: Connection type (websocket/sip)
            credentials: Provider credentials (e.g., Twilio account_sid, auth_token)
            webhook_config: Webhook configuration Pydantic model (optional)
            sip_config: SIP configuration Pydantic model (optional)

        Returns:
            Created telephony config as dict
        """
        logger.info(
            f'Creating telephony config - display_name: {display_name}, provider: {provider}, connection_type: {connection_type}'
        )

        config = await self.telephony_config_repository.create(
            display_name=display_name,
            description=description,
            provider=provider,
            connection_type=connection_type,
            credentials=json.dumps(credentials),
            webhook_config=(
                json.dumps(webhook_config.model_dump()) if webhook_config else None
            ),
            sip_config=json.dumps(sip_config.model_dump()) if sip_config else None,
        )

        # Convert to dict
        config_dict = config.to_dict(exclude_credentials=False)

        # Cache the config
        cache_key = get_telephony_config_cache_key(config.id)
        self.cache_manager.add(
            cache_key, json.dumps(config_dict), expiry=self.telephony_config_cache_time
        )

        # Invalidate list cache
        list_cache_key = get_telephony_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('telephony_config', config.id, 'create')

        logger.info(f'Successfully created telephony config with id: {config.id}')
        return config_dict

    async def get_config(self, config_id: UUID) -> Optional[dict]:
        """
        Get a telephony configuration by ID (with caching)

        Args:
            config_id: UUID of the configuration

        Returns:
            Telephony config as dict or None if not found
        """
        cache_key = get_telephony_config_cache_key(config_id)

        # Try cache first
        cached_config_str = self.cache_manager.get_str(cache_key)
        if cached_config_str:
            logger.info(f'Cache hit for telephony config: {config_id}')
            return json.loads(cached_config_str)

        # Cache miss - fetch from DB
        logger.info(f'Cache miss - fetching telephony config from DB: {config_id}')
        config = await self.telephony_config_repository.find_one(
            id=config_id, is_deleted=False
        )

        if config:
            # Convert to dict and cache
            config_dict = config.to_dict(exclude_credentials=False)
            self.cache_manager.add(
                cache_key,
                json.dumps(config_dict),
                expiry=self.telephony_config_cache_time,
            )
            return config_dict

        return None

    async def list_configs(self) -> List[dict]:
        """
        List all telephony configurations (with caching)

        Returns:
            List of telephony configs as dicts
        """
        list_cache_key = get_telephony_configs_list_cache_key()

        # Try cache first
        cached_list_str = self.cache_manager.get_str(list_cache_key)
        if cached_list_str:
            logger.info('Cache hit for telephony configs list')
            return json.loads(cached_list_str)

        # Cache miss - fetch from DB
        logger.info('Cache miss - fetching telephony configs list from DB')
        configs = await self.telephony_config_repository.find(is_deleted=False)

        # Convert to dicts and cache
        configs_dicts = [
            config.to_dict(exclude_credentials=False) for config in configs
        ]
        self.cache_manager.add(
            list_cache_key,
            json.dumps(configs_dicts),
            expiry=self.telephony_config_cache_time,
        )

        return configs_dicts

    async def update_config(self, config_id: UUID, **update_data) -> Optional[dict]:
        """
        Update a telephony configuration

        Args:
            config_id: UUID of the configuration
            **update_data: Fields to update

        Returns:
            Updated config as dict or None if not found

        Raises:
            ValueError: If validation fails (e.g., SIP connection without sip_config)
        """
        logger.info(f'Updating telephony config: {config_id}')

        existing_config = await self.telephony_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return None

        # Validate connection type requirements after merge
        final_connection_type = update_data.get(
            'connection_type', existing_config.connection_type
        )
        final_sip_config = update_data.get('sip_config', existing_config.sip_config)

        # If final state is SIP connection, ensure sip_config exists
        if final_connection_type == 'sip' and not final_sip_config:
            raise ValueError(
                'sip_config is required for SIP connection type. '
                'Provide sip_config or change connection_type.'
            )

        updated_config = await self.telephony_config_repository.find_one_and_update(
            {'id': config_id}, refresh=True, **update_data
        )

        # Invalidate caches
        cache_key = get_telephony_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_telephony_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('telephony_config', config_id, 'update')

        logger.info(f'Successfully updated telephony config: {config_id}')
        return updated_config.to_dict(exclude_credentials=False)

    async def delete_config(self, config_id: UUID) -> bool:
        """
        Delete a telephony configuration (soft delete)

        Args:
            config_id: UUID of the configuration

        Returns:
            True if deleted, False if not found
        """
        logger.info(f'Deleting telephony config: {config_id}')

        existing_config = await self.telephony_config_repository.find_one(
            id=config_id, is_deleted=False
        )
        if not existing_config:
            return False

        await self.telephony_config_repository.find_one_and_update(
            {'id': config_id}, is_deleted=True
        )

        # Invalidate caches
        cache_key = get_telephony_config_cache_key(config_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_telephony_configs_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('telephony_config', config_id, 'delete')

        logger.info(f'Successfully deleted telephony config: {config_id}')
        return True
