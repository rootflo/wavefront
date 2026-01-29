import json
import uuid
from typing import List, Optional, Tuple
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
from voice_agents_module.utils.language_validation import (
    validate_languages_for_configs,
    validate_default_language,
    format_language_prompt,
)
from voice_agents_module.utils.phone_validation import validate_phone_numbers


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

    def _validate_tts_stt_parameters(
        self,
        tts_voice_ids: dict,
        supported_languages: List[str],
        tts_parameters: Optional[dict] = None,
        stt_parameters: Optional[dict] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate TTS/STT parameters.

        Args:
            tts_voice_ids: TTS voice identifiers dict (language -> voice_id)
            supported_languages: List of supported language codes
            tts_parameters: Provider-specific TTS parameters
            stt_parameters: Provider-specific STT parameters

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        # Validate TTS voice_ids is a dict
        if not isinstance(tts_voice_ids, dict):
            return False, 'TTS voice_ids must be a dictionary'

        if not tts_voice_ids:
            return False, 'TTS voice_ids dictionary cannot be empty'

        # Validate all languages have voice IDs
        supported_set = set(supported_languages)
        provided_set = set(tts_voice_ids.keys())

        missing_langs = supported_set - provided_set
        if missing_langs:
            return False, f'Missing voice IDs for languages: {sorted(missing_langs)}'

        extra_langs = provided_set - supported_set
        if extra_langs:
            return (
                False,
                f'Voice IDs provided for unsupported languages: {sorted(extra_langs)}',
            )

        # Validate each voice_id is non-empty
        for lang, voice_id in tts_voice_ids.items():
            if not voice_id or not str(voice_id).strip():
                return False, f'Voice ID for language "{lang}" cannot be empty'

        # Validate TTS parameters is a dict if provided
        if tts_parameters is not None and not isinstance(tts_parameters, dict):
            return False, 'TTS parameters must be a dictionary'

        # Validate STT parameters is a dict if provided
        if stt_parameters is not None and not isinstance(stt_parameters, dict):
            return False, 'STT parameters must be a dictionary'

        return True, None

    async def _validate_language_and_phone_config(
        self,
        inbound_numbers: List[str],
        outbound_numbers: List[str],
        supported_languages: List[str],
        default_language: str,
        tts_config_id: UUID,
        stt_config_id: UUID,
        agent_id: Optional[UUID] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate language and phone number configuration.

        Args:
            inbound_numbers: List of inbound phone numbers
            outbound_numbers: List of outbound phone numbers
            supported_languages: List of language codes
            default_language: Default language code
            tts_config_id: TTS config ID
            stt_config_id: STT config ID
            agent_id: Agent ID (for update operations, to exclude self from uniqueness check)

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        # Validate phone numbers format
        is_valid, error = validate_phone_numbers(inbound_numbers, 'inbound_numbers')
        if not is_valid:
            return False, error

        is_valid, error = validate_phone_numbers(outbound_numbers, 'outbound_numbers')
        if not is_valid:
            return False, error

        # Validate inbound number uniqueness
        for number in inbound_numbers:
            # Query all agents and check if number is already assigned
            all_agents = await self.voice_agent_repository.find(is_deleted=False)
            for agent in all_agents:
                # Skip self when updating
                if agent_id and agent.id == agent_id:
                    continue

                agent_dict = agent.to_dict()
                if number in agent_dict.get('inbound_numbers', []):
                    return (
                        False,
                        f"Inbound number {number} is already assigned to agent '{agent.name}' (ID: {agent.id})",
                    )

        # Validate default language in supported languages
        is_valid, error = validate_default_language(
            default_language, supported_languages
        )
        if not is_valid:
            return False, error

        # Fetch TTS and STT configs to get providers
        tts_config = await self.tts_config_service.get_config(tts_config_id)
        stt_config = await self.stt_config_service.get_config(stt_config_id)

        if not tts_config or not stt_config:
            return False, 'TTS or STT config not found'

        # Validate languages against provider capabilities
        is_valid, error = validate_languages_for_configs(
            supported_languages, tts_config['provider'], stt_config['provider']
        )
        if not is_valid:
            return False, error

        return True, None

    async def _generate_and_upload_welcome_audio(
        self,
        welcome_message: str,
        tts_config_id: UUID,
        tts_voice_ids: dict,
        tts_parameters: Optional[dict],
        agent_id: UUID,
        supported_languages: List[str],
        default_language: str,
    ) -> None:
        """
        Generate TTS audio for welcome message and upload to cloud storage.
        If multiple languages supported, concatenates language selection prompt.

        Args:
            welcome_message: Text of the welcome message
            tts_config_id: TTS config ID to use for generation
            tts_voice_ids: Voice IDs dict (language -> voice_id)
            tts_parameters: Provider-specific TTS parameters
            agent_id: Voice agent ID (used for generating storage key)
            supported_languages: List of supported language codes
            default_language: Default language code for audio generation

        Raises:
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Generating welcome message audio for agent {agent_id}')

        # Fetch TTS config (credentials only)
        tts_config = await self.tts_config_service.get_config(tts_config_id)
        if not tts_config:
            raise ValueError(f'TTS config {tts_config_id} not found')

        # Get voice ID for default language
        voice_id_for_default = tts_voice_ids.get(default_language)
        if not voice_id_for_default:
            raise ValueError(
                f'No voice ID found for default language: {default_language}'
            )

        # Build welcome audio text
        audio_text = welcome_message

        # If multiple languages supported, append language selection prompt
        if len(supported_languages) > 1:
            language_list = format_language_prompt(supported_languages)
            audio_text = (
                f'{welcome_message}. '
                f'Which language would you like to continue in? {language_list}.'
            )

        logger.info(f'Welcome audio text: {audio_text}')

        # Merge config credentials with agent's voice and parameters
        tts_config_with_params = {
            'provider': tts_config['provider'],
            'api_key': tts_config['api_key'],
            'voice_id': voice_id_for_default,  # Use default language voice
            'parameters': tts_parameters or {},
        }

        # Add language to parameters for TTS generation
        tts_config_with_params['parameters']['language'] = default_language

        # Generate audio using TTS service
        try:
            audio_bytes = await self.tts_generator_service.generate_audio(
                audio_text, tts_config_with_params
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
        tts_voice_ids: dict,
        description: Optional[str] = None,
        conversation_config: Optional[dict] = None,
        status: str = 'inactive',
        inbound_numbers: Optional[List[str]] = None,
        outbound_numbers: Optional[List[str]] = None,
        supported_languages: Optional[List[str]] = None,
        default_language: str = 'en',
        tts_parameters: Optional[dict] = None,
        stt_parameters: Optional[dict] = None,
    ) -> dict:
        """
        Create a new voice agent with inbound/outbound numbers and language support

        Args:
            name: Name of the voice agent
            llm_config_id: LLM config ID
            tts_config_id: TTS config ID
            stt_config_id: STT config ID
            telephony_config_id: Telephony config ID
            system_prompt: System prompt for the agent
            welcome_message: Welcome message text (will be converted to audio)
            tts_voice_ids: TTS voice identifiers per language
            description: Description of the agent (optional)
            conversation_config: Conversation configuration (optional)
            status: Agent status (default: inactive)
            inbound_numbers: Phone numbers for receiving inbound calls (E.164 format)
            outbound_numbers: Phone numbers for making outbound calls (E.164 format)
            supported_languages: List of supported language codes (e.g., ["en", "es", "hi"])
            default_language: Default language code (must be in supported_languages)
            tts_parameters: Provider-specific TTS parameters (optional)
            stt_parameters: Provider-specific STT parameters (optional)

        Returns:
            Created voice agent as dict

        Raises:
            ValueError: If any validation fails
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Creating voice agent: {name}')

        # Set defaults
        inbound_numbers = inbound_numbers or []
        outbound_numbers = outbound_numbers or []
        supported_languages = supported_languages or ['en']

        # Validate all foreign keys
        is_valid, error_message = await self._validate_foreign_keys(
            llm_config_id, tts_config_id, stt_config_id, telephony_config_id
        )
        if not is_valid:
            logger.error(f'FK validation failed: {error_message}')
            raise ValueError(error_message)

        # Validate TTS/STT parameters
        is_valid, error_message = self._validate_tts_stt_parameters(
            tts_voice_ids, supported_languages, tts_parameters, stt_parameters
        )
        if not is_valid:
            logger.error(f'TTS/STT validation failed: {error_message}')
            raise ValueError(error_message)

        # Validate language and phone configuration
        is_valid, error_message = await self._validate_language_and_phone_config(
            inbound_numbers,
            outbound_numbers,
            supported_languages,
            default_language,
            tts_config_id,
            stt_config_id,
        )
        if not is_valid:
            logger.error(f'Language/phone validation failed: {error_message}')
            raise ValueError(error_message)

        # Generate agent ID first
        agent_id = uuid.uuid4()

        # Generate and upload welcome message audio BEFORE creating agent
        # If this fails, no agent record is created
        await self._generate_and_upload_welcome_audio(
            welcome_message,
            tts_config_id,
            tts_voice_ids,
            tts_parameters,
            agent_id,
            supported_languages,
            default_language,
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
            tts_voice_ids=tts_voice_ids,
            tts_parameters=tts_parameters,
            stt_parameters=stt_parameters,
            inbound_numbers=inbound_numbers,
            outbound_numbers=outbound_numbers,
            supported_languages=supported_languages,
            default_language=default_language,
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

        # Invalidate inbound number cache for each number
        for number in inbound_numbers:
            await self._invalidate_inbound_number_cache(number)

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
            ValueError: If any validation fails
            Exception: If TTS generation or upload fails
        """
        logger.info(f'Updating voice agent: {agent_id}')

        existing_agent = await self.voice_agent_repository.find_one(
            id=agent_id, is_deleted=False
        )
        if not existing_agent:
            return None

        existing_dict = existing_agent.to_dict()

        # Track old inbound numbers for cache invalidation
        old_inbound_numbers = existing_dict.get('inbound_numbers', [])
        new_inbound_numbers = update_data.get('inbound_numbers', old_inbound_numbers)

        # Check if language/phone config is being updated
        language_phone_fields = [
            'inbound_numbers',
            'outbound_numbers',
            'supported_languages',
            'default_language',
        ]
        if any(key in update_data for key in language_phone_fields):
            # Build full config (use existing if not being updated)
            inbound_numbers = update_data.get('inbound_numbers', old_inbound_numbers)
            outbound_numbers = update_data.get(
                'outbound_numbers', existing_dict.get('outbound_numbers', [])
            )
            supported_languages = update_data.get(
                'supported_languages', existing_dict.get('supported_languages', ['en'])
            )
            default_language = update_data.get(
                'default_language', existing_dict.get('default_language', 'en')
            )
            tts_config_id = update_data.get(
                'tts_config_id', existing_agent.tts_config_id
            )
            stt_config_id = update_data.get(
                'stt_config_id', existing_agent.stt_config_id
            )

            # Validate language/phone config (pass agent_id to exclude self from uniqueness check)
            is_valid, error_message = await self._validate_language_and_phone_config(
                inbound_numbers,
                outbound_numbers,
                supported_languages,
                default_language,
                tts_config_id,
                stt_config_id,
                agent_id=agent_id,
            )
            if not is_valid:
                logger.error(f'Language/phone validation failed: {error_message}')
                raise ValueError(error_message)

        # Validate TTS/STT parameters if being updated
        tts_stt_fields = [
            'tts_voice_ids',
            'tts_parameters',
            'stt_parameters',
            'supported_languages',
        ]
        if any(key in update_data for key in tts_stt_fields):
            tts_voice_ids = update_data.get(
                'tts_voice_ids', existing_agent.tts_voice_ids
            )
            supported_languages_for_validation = update_data.get(
                'supported_languages', existing_dict.get('supported_languages', ['en'])
            )
            tts_parameters = update_data.get(
                'tts_parameters', existing_dict.get('tts_parameters')
            )
            stt_parameters = update_data.get(
                'stt_parameters', existing_dict.get('stt_parameters')
            )

            is_valid, error_message = self._validate_tts_stt_parameters(
                tts_voice_ids,
                supported_languages_for_validation,
                tts_parameters,
                stt_parameters,
            )
            if not is_valid:
                logger.error(f'TTS/STT validation failed: {error_message}')
                raise ValueError(error_message)

        # Check if welcome_message or language config changed (requires audio regeneration)
        audio_regeneration_needed = False
        if (
            'welcome_message' in update_data
            and update_data['welcome_message'] != existing_agent.welcome_message
        ):
            audio_regeneration_needed = True
        if 'supported_languages' in update_data and update_data[
            'supported_languages'
        ] != existing_dict.get('supported_languages'):
            audio_regeneration_needed = True
        if 'default_language' in update_data and update_data[
            'default_language'
        ] != existing_dict.get('default_language'):
            audio_regeneration_needed = True
        if 'tts_voice_ids' in update_data and update_data[
            'tts_voice_ids'
        ] != existing_dict.get('tts_voice_ids'):
            audio_regeneration_needed = True
        if 'tts_parameters' in update_data and update_data[
            'tts_parameters'
        ] != existing_dict.get('tts_parameters'):
            audio_regeneration_needed = True
        if 'tts_config_id' in update_data and update_data[
            'tts_config_id'
        ] != existing_dict.get('tts_config_id'):
            audio_regeneration_needed = True

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

        # Regenerate welcome audio if needed
        if audio_regeneration_needed:
            logger.info(
                'Welcome message or language config changed, regenerating audio'
            )
            try:
                # Use updated values if provided, otherwise use existing
                welcome_message = update_data.get(
                    'welcome_message', existing_agent.welcome_message
                )
                tts_config_id = update_data.get(
                    'tts_config_id', existing_agent.tts_config_id
                )
                tts_voice_ids = update_data.get(
                    'tts_voice_ids', existing_agent.tts_voice_ids
                )
                tts_parameters = update_data.get(
                    'tts_parameters', existing_dict.get('tts_parameters')
                )
                supported_languages = update_data.get(
                    'supported_languages',
                    existing_dict.get('supported_languages', ['en']),
                )
                default_language = update_data.get(
                    'default_language', existing_dict.get('default_language', 'en')
                )

                await self._generate_and_upload_welcome_audio(
                    welcome_message,
                    tts_config_id,
                    tts_voice_ids,
                    tts_parameters,
                    agent_id,
                    supported_languages,
                    default_language,
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

        # Invalidate inbound number cache if numbers changed
        if old_inbound_numbers != new_inbound_numbers:
            # Invalidate old numbers
            for number in old_inbound_numbers:
                if number not in new_inbound_numbers:
                    await self._invalidate_inbound_number_cache(number)
            # Invalidate new numbers
            for number in new_inbound_numbers:
                await self._invalidate_inbound_number_cache(number)

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

    async def _invalidate_inbound_number_cache(self, phone_number: str):
        """Invalidate cache for inbound number lookup in call_processing"""
        # Invalidate local cache
        cache_key = f'inbound_number:{phone_number}'
        self.cache_manager.remove(cache_key)

        # Also invalidate in call_processing
        await invalidate_call_processing_cache('inbound_number', phone_number, 'update')

    async def get_agent_by_inbound_number(self, phone_number: str) -> Optional[dict]:
        """
        Get voice agent by inbound phone number (with caching).

        Args:
            phone_number: E.164 formatted phone number

        Returns:
            Voice agent dict or None if not found
        """
        cache_key = f'inbound_number:{phone_number}'

        # Try cache first
        cached_agent_id = self.cache_manager.get_str(cache_key)
        if cached_agent_id:
            logger.info(f'Cache hit for inbound number: {phone_number}')
            return await self.get_agent(UUID(cached_agent_id))

        # Cache miss - query database
        logger.info(f'Cache miss - fetching agent by inbound number: {phone_number}')
        all_agents = await self.voice_agent_repository.find(is_deleted=False)

        for agent in all_agents:
            agent_dict = agent.to_dict()
            if phone_number in agent_dict.get('inbound_numbers', []):
                # Cache the mapping
                self.cache_manager.add(
                    cache_key, str(agent.id), expiry=self.voice_agent_cache_time
                )
                return agent_dict

        return None
