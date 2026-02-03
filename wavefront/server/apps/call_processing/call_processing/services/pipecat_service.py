"""
Pipecat pipeline orchestration service

Creates and runs the voice conversation pipeline using configured STT/LLM/TTS services
"""

from typing import Dict, Any, List
from copy import deepcopy
from call_processing.log.logger import logger
from call_processing.services.tool_wrapper_service import ToolWrapperFactory

# Pipecat core imports
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import Frame
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.processors.transcript_processor import (
    TranscriptProcessor,
)

# from pipecat.pipeline.service_switcher import (
#     ServiceSwitcher,
#     ServiceSwitcherStrategyManual,
# )
from pipecat.transports.base_transport import BaseTransport
from pipecat.turns.user_mute import (
    FunctionCallUserMuteStrategy,
    # MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import (
    VADUserTurnStartStrategy,
    # MinWordsUserTurnStartStrategy,
)
from pipecat.turns.user_stop import (
    TurnAnalyzerUserTurnStopStrategy,
    #  TranscriptionUserTurnStopStrategy
)
from call_processing.services.stt_service import STTServiceFactory
from call_processing.services.tts_service import TTSServiceFactory
from call_processing.services.llm_service import LLMServiceFactory
from call_processing.services.conversation_completion_tool import (
    ConversationCompletionToolFactory,
)
from call_processing.constants.language_config import (
    LANGUAGE_INSTRUCTIONS,
)


class STTLanguageSwitcher(ParallelPipeline):
    """
    ParallelPipeline that routes STT to different language-specific services
    based on current language state. Same pattern as LanguageSwitcher for TTS.
    """

    def __init__(
        self,
        stt_services: Dict[str, Any],
        supported_languages: List[str],
        default_language: str,
    ):
        self._current_language = default_language
        self._stt_services = stt_services
        self._supported_languages = supported_languages

        # Build parallel routes: one per language
        routes = []
        for lang_code in supported_languages:
            filter_func = self._create_language_filter(lang_code)
            stt_service = stt_services[lang_code]
            routes.append([FunctionFilter(filter_func), stt_service])

        super().__init__(*routes)

    def _create_language_filter(self, lang_code: str):
        """Create filter function for specific language"""

        async def language_filter(_: Frame) -> bool:
            return self._current_language == lang_code

        return language_filter

    @property
    def current_language(self):
        return self._current_language

    def set_language(self, language_code: str):
        """Update current language (called by language detection tool)"""
        if language_code in self._supported_languages:
            self._current_language = language_code
            logger.info(f'STTLanguageSwitcher: Language set to {language_code}')
        else:
            logger.warning(f'STTLanguageSwitcher: Invalid language {language_code}')


class LanguageSwitcher(ParallelPipeline):
    """
    ParallelPipeline that routes TTS to different language-specific services
    based on current language state.
    """

    def __init__(
        self,
        tts_services: Dict[str, Any],
        supported_languages: List[str],
        default_language: str,
    ):
        self._current_language = default_language
        self._tts_services = tts_services
        self._supported_languages = supported_languages

        # Build parallel routes: one per language
        # Each route: [FunctionFilter, TTS service]
        routes = []
        for lang_code in supported_languages:
            filter_func = self._create_language_filter(lang_code)
            tts_service = tts_services[lang_code]
            routes.append([FunctionFilter(filter_func), tts_service])

        super().__init__(*routes)

    def _create_language_filter(self, lang_code: str):
        """Create filter function for specific language"""

        async def language_filter(_: Frame) -> bool:
            return self._current_language == lang_code

        return language_filter

    @property
    def current_language(self):
        return self._current_language

    def set_language(self, language_code: str):
        """Update current language (called by language detection tool)"""
        if language_code in self._supported_languages:
            self._current_language = language_code
            logger.info(f'LanguageSwitcher: Language set to {language_code}')
        else:
            logger.warning(f'LanguageSwitcher: Invalid language {language_code}')


class PipecatService:
    """Service for creating and running Pipecat pipelines"""

    async def run_conversation(
        self,
        transport: BaseTransport,
        agent_config: Dict[str, Any],
        llm_config: Dict[str, Any],
        tts_config: Dict[str, Any],
        stt_config: Dict[str, Any],
        tools: List[Dict[str, Any]],
        customer_number: str,
    ):
        """
        Create and run the Pipecat pipeline for a voice conversation

        Args:
            transport: Pipecat transport (e.g., WebSocket transport from Twilio)
            agent_config: Voice agent configuration including system_prompt,
                          supported_languages, default_language, tts_voice_id, tts_parameters, stt_parameters
            llm_config: LLM provider configuration
            tts_config: TTS provider configuration (credentials only)
            stt_config: STT provider configuration (credentials only)
            tools: List of tool dicts with association details
        """
        # Extract language configuration from agent_config
        supported_languages = agent_config.get('supported_languages', ['en'])
        default_language = agent_config.get('default_language', 'en')
        is_multi_language = len(supported_languages) > 1

        # Extract TTS/STT parameters from agent
        tts_voice_ids_dict = agent_config.get(
            'tts_voice_ids', {}
        )  # Dict of language -> voice_id
        tts_parameters = agent_config.get('tts_parameters', {})
        stt_parameters = agent_config.get('stt_parameters', {})

        logger.info(f"Starting conversation for agent: {agent_config['name']}")
        logger.info(
            f'Language config - supported: {supported_languages}, '
            f'default: {default_language}, multi-language: {is_multi_language}'
        )

        # Track language state for multi-language conversations
        language_state = {
            'current_language': default_language,
            'switch_count': 0,
            'original_system_prompt': '',
        }

        # Create LLM service (language-agnostic)
        llm = LLMServiceFactory.create_llm_service(llm_config)

        # Get voice ID for default language
        default_voice_id = tts_voice_ids_dict.get(default_language, 'default')

        # Merge TTS config credentials with agent's voice and parameters
        tts_config_with_params = {
            'provider': tts_config['provider'],
            'api_key': tts_config['api_key'],
            'voice_id': default_voice_id,  # Will be overridden per language in multi-lang mode
            'parameters': tts_parameters or {},
        }

        # Merge STT config credentials with agent's parameters
        stt_config_with_params = {
            'provider': stt_config['provider'],
            'api_key': stt_config['api_key'],
            'parameters': stt_parameters or {},
        }

        # Create TTS services (one per language for multi-language mode)
        tts_services = {}

        if is_multi_language:
            logger.info(
                f'Multi-language mode enabled for languages: {supported_languages}'
            )

            # Create TTS services for each supported language
            for lang_code in supported_languages:
                # Get voice ID for this language
                voice_id_for_lang = tts_voice_ids_dict.get(lang_code)
                if not voice_id_for_lang:
                    logger.warning(
                        f'No voice ID for language {lang_code}, using default'
                    )
                    voice_id_for_lang = default_voice_id

                # Deep clone config to avoid mutating original
                tts_config_lang = deepcopy(tts_config_with_params)

                # Update language parameters
                if 'parameters' not in tts_config_lang:
                    tts_config_lang['parameters'] = {}
                tts_config_lang['parameters']['language'] = lang_code
                tts_config_lang['voice_id'] = voice_id_for_lang

                # Create TTS service
                tts_services[lang_code] = TTSServiceFactory.create_tts_service(
                    tts_config_lang
                )
                logger.info(
                    f'Created TTS service for language: {lang_code} '
                    f'with voice: {voice_id_for_lang}'
                )

            # Create per-language STT services (same pattern as TTS)
            stt_services = {}
            for lang_code in supported_languages:
                stt_config_lang = deepcopy(stt_config_with_params)
                if 'parameters' not in stt_config_lang:
                    stt_config_lang['parameters'] = {}
                stt_config_lang['parameters']['language'] = lang_code

                stt_services[lang_code] = STTServiceFactory.create_stt_service(
                    stt_config_lang
                )
                logger.info(f'Created STT service for language: {lang_code}')

            # Create STTLanguageSwitcher for STT routing
            stt = STTLanguageSwitcher(
                stt_services=stt_services,
                supported_languages=supported_languages,
                default_language=default_language,
            )
            logger.info(
                f'Initialized STTLanguageSwitcher with default language: {default_language}'
            )

            # Create LanguageSwitcher for TTS routing
            tts = LanguageSwitcher(
                tts_services=tts_services,
                supported_languages=supported_languages,
                default_language=default_language,
            )
            logger.info(
                f'Initialized LanguageSwitcher with default language: {default_language}'
            )

        else:
            logger.info('Single language mode - no language detection needed')

            # Create single STT/TTS services using merged configs
            stt = STTServiceFactory.create_stt_service(stt_config_with_params)
            tts = TTSServiceFactory.create_tts_service(tts_config_with_params)

        # Create initial messages with system prompt
        base_system_prompt = (
            f'Customer phone number: {customer_number}\n'
            + agent_config['system_prompt']
        )

        # Add language instruction for default language if multi-language
        if is_multi_language:
            initial_language_instruction = LANGUAGE_INSTRUCTIONS.get(
                default_language, LANGUAGE_INSTRUCTIONS.get('en', 'Respond in English.')
            )
            system_content = f'{base_system_prompt}\n\n{initial_language_instruction}'
            # Store base prompt without language instruction for switching
            language_state['original_system_prompt'] = base_system_prompt
        else:
            system_content = base_system_prompt

        messages = [
            {
                'role': 'system',
                'content': system_content,
            }
        ]

        # Load and register tools for this agent
        function_schemas = []
        agent_id = agent_config.get('id')

        if tools:
            try:
                logger.info(f'Loaded {len(tools)} tools for agent {agent_id}')

                # Create FunctionSchema objects and callable functions for all tools
                (
                    function_schemas,
                    tool_registrations,
                ) = ToolWrapperFactory.create_all_tool_functions(tools)

                # Register each tool with LLM
                for tool_name, tool_func in tool_registrations:
                    llm.register_function(tool_name, tool_func)
                    logger.info(f"Registered tool '{tool_name}' with LLM")

            except Exception as e:
                logger.error(
                    f'Error loading tools for agent {agent_id}: {str(e)}',
                    exc_info=True,
                )
                # Continue without tools rather than failing the call
        else:
            logger.info(f'No tools configured for agent {agent_id}')

        # Create containers for late binding (populated after creation)
        task_container = {'task': None}
        context_container = {'context': None}

        # Register language detection tool if multi-language enabled
        if is_multi_language:
            from call_processing.services.language_detection_tool import (
                LanguageDetectionToolFactory,
            )

            language_detection_func = (
                LanguageDetectionToolFactory.create_language_detection_tool(
                    task_container=task_container,
                    language_switcher=tts,  # Pass the TTS LanguageSwitcher instance
                    stt_language_switcher=stt,  # Pass the STT LanguageSwitcher instance
                    context_container=context_container,
                    supported_languages=supported_languages,
                    default_language=default_language,
                    language_state=language_state,
                )
            )

            llm.register_function('detect_and_switch_language', language_detection_func)
            logger.info('Registered language detection tool with LLM')

        # Register conversation completion tool
        conversation_completion_func = (
            ConversationCompletionToolFactory.create_conversation_completion_tool(
                task_container=task_container
            )
        )
        llm.register_function('end_conversation', conversation_completion_func)
        logger.info('Registered conversation completion tool with LLM')

        # Create FunctionSchema for conversation completion
        end_conversation_schema = FunctionSchema(
            name='end_conversation',
            description=(
                'Call this function when the user indicates they want to end the conversation. '
                'This includes goodbye phrases, expressions of completion, or any indication '
                'that the user wants to hang up or finish the call. Examples: "goodbye", "bye", '
                '"thank you", "that\'s all", "I\'m done", etc.'
            ),
            properties={
                'farewell_message': {
                    'type': 'string',
                    'description': (
                        'Optional custom farewell message to say to the user before ending. '
                        'If not provided, uses default: "Thank you for using our service! Goodbye!"'
                    ),
                }
            },
            required=[],
        )

        # Create FunctionSchema for language detection (if multi-language)
        language_detection_schemas = []
        if is_multi_language:
            language_detection_schema = FunctionSchema(
                name='detect_and_switch_language',
                description=(
                    f"Detect and switch the conversation language. Call this whenever the user "
                    f"indicates a language preference, including: responding with a language name "
                    f"(e.g., 'Hindi', 'Spanish', 'English'), requesting a switch (e.g., 'switch to Hindi', "
                    f"'I want to speak in Spanish'), or selecting a language when asked for their preference. "
                    f"Even a single word like 'Hindi' or 'Spanish' should trigger this tool if it refers to a language choice. "
                    f"Supported languages: {', '.join(supported_languages)}. "
                    f"Current language: {language_state['current_language']}."
                ),
                properties={
                    'target_language': {
                        'type': 'string',
                        'description': f"Target language code. Must be one of: {', '.join(supported_languages)}",
                        'enum': supported_languages,
                    },
                    'user_intent': {
                        'type': 'string',
                        'description': "The user's statement indicating language preference (for logging)",
                    },
                },
                required=['target_language', 'user_intent'],
            )
            language_detection_schemas.append(language_detection_schema)

        # Combine all FunctionSchema objects for ToolsSchema
        all_function_schemas = (
            [end_conversation_schema] + language_detection_schemas + function_schemas
        )
        tools_schema = ToolsSchema(standard_tools=all_function_schemas)

        # Create LLM context and aggregator
        context = LLMContext(messages, tools=tools_schema)

        # Populate context container for language detection tool (if multi-language)
        if is_multi_language:
            context_container['context'] = context

        context_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                user_turn_strategies=UserTurnStrategies(
                    start=[
                        VADUserTurnStartStrategy(),
                        # MinWordsUserTurnStartStrategy(min_words=3),
                    ],  # List of start strategies
                    stop=[
                        TurnAnalyzerUserTurnStopStrategy(
                            turn_analyzer=LocalSmartTurnAnalyzerV3()
                        ),
                        # TranscriptionUserTurnStopStrategy() # Not needed
                    ],  # List of stop strategies
                ),
                user_mute_strategies=[
                    # MuteUntilFirstBotCompleteUserMuteStrategy(), # Not needed since first message is pre-recorded audio
                    FunctionCallUserMuteStrategy(),
                ],
            ),
        )

        # Create transcript processor for language detection
        transcript = TranscriptProcessor()

        # Build pipeline components list
        pipeline_components = [
            transport.input(),  # Audio input from Twilio
            stt,  # Speech-to-Text (ServiceSwitcher for multi-lang, direct for single)
            transcript.user(),  # Transcript processor for user messages
            context_aggregator.user(),  # Add user message to context
            llm,  # LLM processing
            tts,  # Text-to-Speech (ServiceSwitcher for multi-lang, direct for single)
            transport.output(),  # Audio output to Twilio
            transcript.assistant(),  # Transcript processor for assistant messages
            context_aggregator.assistant(),  # Add assistant response to context
        ]

        # Create pipeline
        pipeline = Pipeline(pipeline_components)

        # Create pipeline task with Twilio-specific parameters
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,  # Twilio uses 8kHz
                audio_out_sample_rate=8000,
                enable_metrics=True,
                # enable_usage_metrics=True,
                # report_only_initial_ttfb=True
            ),
            idle_timeout_secs=20,
        )

        # Populate task container for language detection tool (if multi-language)
        task_container['task'] = task

        # Register event handlers
        @transport.event_handler('on_client_connected')
        async def on_client_connected(transport, client):
            logger.info(f"Client connected for agent: {agent_config['name']}")
            # Bot waits for user to speak first (can be changed to greet first)

        @transport.event_handler('on_client_disconnected')
        async def on_client_disconnected(transport, client):
            logger.info(f"Client disconnected for agent: {agent_config['name']}")
            await task.cancel()

        # Run pipeline
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

        logger.info(f"Conversation ended for agent: {agent_config['name']}")
