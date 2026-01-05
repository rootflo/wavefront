import json
import uuid
from typing import List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.voice_agent import VoiceAgent
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from voice_agents_module.services.telephony_config_service import (
    TelephonyConfigService,
)
from voice_agents_module.services.tts_config_service import TtsConfigService
from voice_agents_module.services.stt_config_service import SttConfigService
from voice_agents_module.services.tts_generator_service import TTSGeneratorService
from voice_agents_module.utils.cache_utils import (
    get_voice_agent_cache_key,
    get_voice_agents_list_cache_key,
    get_welcome_message_url_cache_key,
)
from voice_agents_module.utils.cache_invalidation import (
    invalidate_call_processing_cache,
)
from voice_agents_module.utils.storage_utils import generate_welcome_message_key


class VoiceAgentService:
    """Service for handling voice agent CRUD operations with caching"""

    def __init__(
        self,
        voice_agent_repository: SQLAlchemyRepository[VoiceAgent],
        telephony_config_service: TelephonyConfigService,
        tts_config_service: TtsConfigService,
        stt_config_service: SttConfigService,
        llm_config_repository: SQLAlchemyRepository[LlmInferenceConfig],
        cache_manager: CacheManager,
        tts_generator_service: TTSGeneratorService,
        cloud_storage_manager: CloudStorageManager,
        voice_agent_bucket: str,
    ):
        """
        Initialize the voice agent service

        Args:
            voice_agent_repository: Repository for voice agents
            telephony_config_service: Service for telephony configs
            tts_config_service: Service for TTS configs
            stt_config_service: Service for STT configs
            llm_config_repository: Repository for LLM inference configs
            cache_manager: Cache manager instance
            tts_generator_service: Service for generating TTS audio
            cloud_storage_manager: Cloud storage manager for uploading audio
            voice_agent_bucket: Bucket name for storing voice agent audio files
        """
        self.voice_agent_repository = voice_agent_repository
        self.telephony_config_service = telephony_config_service
        self.tts_config_service = tts_config_service
        self.stt_config_service = stt_config_service
        self.llm_config_repository = llm_config_repository
        self.cache_manager = cache_manager
        self.tts_generator_service = tts_generator_service
        self.cloud_storage_manager = cloud_storage_manager
        self.voice_agent_bucket = voice_agent_bucket
        self.voice_agent_cache_time = 3600 * 24

    async def _validate_foreign_keys(
        self,
        llm_config_id: UUID,
        tts_config_id: UUID,
        stt_config_id: UUID,
        telephony_config_id: UUID,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all foreign key IDs exist and are not deleted

        Args:
            llm_config_id: LLM config ID
            tts_config_id: TTS config ID
            stt_config_id: STT config ID
            telephony_config_id: Telephony config ID

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate LLM config
        llm_config = await self.llm_config_repository.find_one(
            id=llm_config_id, is_deleted=False
        )
        if not llm_config:
            return False, f'LLM config with ID {llm_config_id} not found or deleted'

        # Validate TTS config
        tts_config = await self.tts_config_service.get_config(tts_config_id)
        if not tts_config:
            return False, f'TTS config with ID {tts_config_id} not found or deleted'

        # Validate STT config
        stt_config = await self.stt_config_service.get_config(stt_config_id)
        if not stt_config:
            return False, f'STT config with ID {stt_config_id} not found or deleted'

        # Validate Telephony config
        telephony_config = await self.telephony_config_service.get_config(
            telephony_config_id
        )
        if not telephony_config:
            return (
                False,
                f'Telephony config with ID {telephony_config_id} not found or deleted',
            )

        return True, None

    async def _generate_and_upload_welcome_audio(
        self, welcome_message: str, tts_config_id: UUID, agent_id: UUID
    ) -> None:
        """
        Generate TTS audio for welcome message and upload to cloud storage

        Args:
            welcome_message: Text of the welcome message
            tts_config_id: TTS config ID to use for generation
            agent_id: Voice agent ID (used for generating storage key)

        Raises:
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Generating welcome message audio for agent {agent_id}')

        # Fetch TTS config
        tts_config = await self.tts_config_service.get_config(tts_config_id)
        if not tts_config:
            raise ValueError(f'TTS config {tts_config_id} not found')

        # Generate audio using TTS service
        try:
            audio_bytes = await self.tts_generator_service.generate_audio(
                welcome_message, tts_config
            )
            logger.info(f'Generated audio: {len(audio_bytes)} bytes')
        except Exception as e:
            logger.error(f'Failed to generate TTS audio: {str(e)}')
            raise Exception(f'TTS generation failed: {str(e)}')

        # Upload to cloud storage
        try:
            storage_key = generate_welcome_message_key(agent_id)
            self.cloud_storage_manager.save_small_file(
                audio_bytes,
                self.voice_agent_bucket,
                storage_key,
                content_type='audio/mpeg',
            )
            logger.info(f'Uploaded welcome message audio with key: {storage_key}')
        except Exception as e:
            logger.error(f'Failed to upload audio to cloud storage: {str(e)}')
            raise Exception(f'Audio upload failed: {str(e)}')

        # Invalidate cached presigned URL since we uploaded new audio
        url_cache_key = get_welcome_message_url_cache_key(agent_id)
        self.cache_manager.remove(url_cache_key)

    async def create_agent(
        self,
        name: str,
        llm_config_id: UUID,
        tts_config_id: UUID,
        stt_config_id: UUID,
        telephony_config_id: UUID,
        system_prompt: str,
        welcome_message: str,
        description: Optional[str] = None,
        conversation_config: Optional[dict] = None,
        status: str = 'inactive',
    ) -> dict:
        """
        Create a new voice agent

        Args:
            name: Name of the voice agent
            llm_config_id: LLM config ID
            tts_config_id: TTS config ID
            stt_config_id: STT config ID
            telephony_config_id: Telephony config ID
            system_prompt: System prompt for the agent
            welcome_message: Welcome message text (will be converted to audio)
            description: Description of the agent (optional)
            conversation_config: Conversation configuration (optional)
            status: Agent status (default: inactive)

        Returns:
            Created voice agent as dict

        Raises:
            ValueError: If any foreign key validation fails
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Creating voice agent: {name}')

        # Validate all foreign keys
        is_valid, error_message = await self._validate_foreign_keys(
            llm_config_id, tts_config_id, stt_config_id, telephony_config_id
        )
        if not is_valid:
            logger.error(f'FK validation failed: {error_message}')
            raise ValueError(error_message)

        # Generate agent ID first
        agent_id = uuid.uuid4()

        # Generate and upload welcome message audio BEFORE creating agent
        # If this fails, no agent record is created
        await self._generate_and_upload_welcome_audio(
            welcome_message, tts_config_id, agent_id
        )

        # Create agent only if audio generation succeeded
        agent = await self.voice_agent_repository.create(
            id=agent_id,
            name=name,
            description=description,
            llm_config_id=llm_config_id,
            tts_config_id=tts_config_id,
            stt_config_id=stt_config_id,
            telephony_config_id=telephony_config_id,
            system_prompt=system_prompt,
            conversation_config=json.dumps(conversation_config)
            if conversation_config
            else None,
            welcome_message=welcome_message,
            status=status,
        )

        # Convert to dict
        agent_dict = agent.to_dict()

        # Cache the agent
        cache_key = get_voice_agent_cache_key(agent.id)
        self.cache_manager.add(
            cache_key, json.dumps(agent_dict), expiry=self.voice_agent_cache_time
        )

        # Invalidate list cache
        list_cache_key = get_voice_agents_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('voice_agent', agent.id, 'create')

        logger.info(f'Successfully created voice agent with id: {agent.id}')
        return agent_dict

    async def get_agent(self, agent_id: UUID) -> Optional[dict]:
        """
        Get a voice agent by ID (with caching)

        Args:
            agent_id: UUID of the agent

        Returns:
            Voice agent as dict or None if not found
        """
        cache_key = get_voice_agent_cache_key(agent_id)

        # Try cache first
        cached_agent_str = self.cache_manager.get_str(cache_key)
        if cached_agent_str:
            logger.info(f'Cache hit for voice agent: {agent_id}')
            return json.loads(cached_agent_str)

        # Cache miss - fetch from DB
        logger.info(f'Cache miss - fetching voice agent from DB: {agent_id}')
        agent = await self.voice_agent_repository.find_one(
            id=agent_id, is_deleted=False
        )

        if agent:
            # Convert to dict and cache
            agent_dict = agent.to_dict()
            self.cache_manager.add(
                cache_key, json.dumps(agent_dict), expiry=self.voice_agent_cache_time
            )
            return agent_dict

        return None

    async def list_agents(self) -> List[dict]:
        """
        List all voice agents (with caching)

        Returns:
            List of voice agents as dicts
        """
        list_cache_key = get_voice_agents_list_cache_key()

        # Try cache first
        cached_list_str = self.cache_manager.get_str(list_cache_key)
        if cached_list_str:
            logger.info('Cache hit for voice agents list')
            return json.loads(cached_list_str)

        # Cache miss - fetch from DB
        logger.info('Cache miss - fetching voice agents list from DB')
        agents = await self.voice_agent_repository.find(is_deleted=False)

        # Convert to dicts and cache
        agents_dicts = [agent.to_dict() for agent in agents]
        self.cache_manager.add(
            list_cache_key, json.dumps(agents_dicts), expiry=self.voice_agent_cache_time
        )

        return agents_dicts

    async def update_agent(self, agent_id: UUID, **update_data) -> Optional[dict]:
        """
        Update a voice agent

        Args:
            agent_id: UUID of the agent
            **update_data: Fields to update

        Returns:
            Updated agent as dict or None if not found

        Raises:
            ValueError: If any foreign key validation fails
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Updating voice agent: {agent_id}')

        existing_agent = await self.voice_agent_repository.find_one(
            id=agent_id, is_deleted=False
        )
        if not existing_agent:
            return None

        # Check if welcome_message is being updated
        welcome_message_changed = False
        if (
            'welcome_message' in update_data
            and update_data['welcome_message'] != existing_agent.welcome_message
        ):
            welcome_message_changed = True
            new_welcome_message = update_data['welcome_message']

        # If any FK fields are being updated, validate them
        if any(
            key in update_data
            for key in [
                'llm_config_id',
                'tts_config_id',
                'stt_config_id',
                'telephony_config_id',
            ]
        ):
            # Build the full set of FK IDs (use existing if not being updated)
            llm_config_id = update_data.get(
                'llm_config_id', existing_agent.llm_config_id
            )
            tts_config_id = update_data.get(
                'tts_config_id', existing_agent.tts_config_id
            )
            stt_config_id = update_data.get(
                'stt_config_id', existing_agent.stt_config_id
            )
            telephony_config_id = update_data.get(
                'telephony_config_id', existing_agent.telephony_config_id
            )

            is_valid, error_message = await self._validate_foreign_keys(
                llm_config_id, tts_config_id, stt_config_id, telephony_config_id
            )
            if not is_valid:
                logger.error(f'FK validation failed: {error_message}')
                raise ValueError(error_message)

        # If welcome message changed, regenerate audio
        if welcome_message_changed:
            logger.info('Welcome message changed, regenerating audio')
            try:
                # Use updated tts_config_id if provided, otherwise use existing
                tts_config_id = update_data.get(
                    'tts_config_id', existing_agent.tts_config_id
                )
                await self._generate_and_upload_welcome_audio(
                    new_welcome_message, tts_config_id, agent_id
                )
            except Exception as e:
                logger.error(f'Failed to regenerate welcome audio: {str(e)}')
                raise e

        updated_agent = await self.voice_agent_repository.find_one_and_update(
            {'id': agent_id}, refresh=True, **update_data
        )

        # Invalidate caches
        cache_key = get_voice_agent_cache_key(agent_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_voice_agents_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('voice_agent', agent_id, 'update')

        logger.info(f'Successfully updated voice agent: {agent_id}')
        return updated_agent.to_dict()

    async def get_welcome_message_audio_url(self, agent_id: UUID) -> str:
        """
        Generate presigned URL for agent's welcome message audio (with caching)

        Args:
            agent_id: UUID of the voice agent

        Returns:
            str: Presigned HTTPS URL (2-hour expiration) or empty string if no welcome message

        Raises:
            Exception: If presigned URL generation fails
        """
        url_cache_key = get_welcome_message_url_cache_key(agent_id)

        # Try cache first
        cached_url = self.cache_manager.get_str(url_cache_key)
        if cached_url:
            logger.info(f'Cache hit for welcome message URL for agent {agent_id}')
            return cached_url

        try:
            # Generate storage key from agent ID
            storage_key = generate_welcome_message_key(agent_id)

            # Generate presigned URL with 2-hour expiration
            presigned_url = self.cloud_storage_manager.generate_presigned_url(
                bucket_name=self.voice_agent_bucket,
                key=storage_key,
                type='get',
                expiresIn=7200,  # 2 hours in seconds
            )

            # Cache the URL with expiry just under 2 hours (100 second buffer)
            self.cache_manager.add(url_cache_key, presigned_url, expiry=7100)

            logger.info(f'Generated and cached presigned URL for agent {agent_id}')
            return presigned_url

        except Exception as e:
            logger.error(
                f'Failed to generate presigned URL for agent {agent_id}: {str(e)}'
            )
            raise Exception(f'Failed to generate welcome message audio URL: {str(e)}')

    async def delete_agent(self, agent_id: UUID) -> bool:
        """
        Delete a voice agent (soft delete)

        Args:
            agent_id: UUID of the agent

        Returns:
            True if deleted, False if not found
        """
        logger.info(f'Deleting voice agent: {agent_id}')

        existing_agent = await self.voice_agent_repository.find_one(
            id=agent_id, is_deleted=False
        )
        if not existing_agent:
            return False

        await self.voice_agent_repository.find_one_and_update(
            {'id': agent_id}, is_deleted=True
        )

        # Invalidate caches
        cache_key = get_voice_agent_cache_key(agent_id)
        self.cache_manager.remove(cache_key)

        list_cache_key = get_voice_agents_list_cache_key()
        self.cache_manager.remove(list_cache_key)

        # Invalidate cache in call_processing
        await invalidate_call_processing_cache('voice_agent', agent_id, 'delete')

        logger.info(f'Successfully deleted voice agent: {agent_id}')
        return True
