"""
Pipecat pipeline orchestration service

Creates and runs the voice conversation pipeline using configured STT/LLM/TTS services
"""

from typing import Dict, Any, List
from copy import deepcopy
import asyncio
import os
import random
from call_processing.log.logger import logger
from call_processing.services.call_evaluation_service import CallEvaluationService
from call_processing.services.tool_wrapper_service import ToolWrapperFactory
from call_processing.utils import get_current_ist_time_str

# Pipecat core imports
from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pipecat.utils.tracing.setup import setup_tracing
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    StopFrame,
    TTSSpeakFrame,
    BotSpeakingFrame,
    BotStartedSpeakingFrame,
    UserSpeakingFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)

# from pipecat.pipeline.service_switcher import (
#     ServiceSwitcher,
#     ServiceSwitcherStrategyManual,
# )
from pipecat.transports.base_transport import BaseTransport
from pipecat.turns.user_mute import (
    FunctionCallUserMuteStrategy,
    MuteUntilFirstBotCompleteUserMuteStrategy,
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

# from call_processing.services.conversation_completion_tool import (
#     ConversationCompletionToolFactory,
# )
from call_processing.constants.language_config import (
    LANGUAGE_INSTRUCTIONS,
    LANGUAGE_DISPLAY_NAMES,
)
from call_processing.constants.filler_phrases import FILLER_PHRASES

ENABLE_TRACING = os.getenv('CALL_PROCESSING_ENABLE_TRACING', 'true').lower() == 'true'
ENABLE_TURN_TRACKING = (
    os.getenv('CALL_PROCESSING_ENABLE_TURN_TRACKING', 'true').lower() == 'true'
)

OTLP_ENDPOINT = os.getenv('CALL_PROCESSING_OTLP_ENDPOINT')

if ENABLE_TRACING and OTLP_ENDPOINT:
    exporter = OTLPSpanExporter(
        endpoint=OTLP_ENDPOINT,
        insecure=True,
    )
    setup_tracing(
        service_name=os.getenv(
            'CALL_PROCESSING_TRACING_SERVICE_NAME', 'call-processing'
        ),
        exporter=exporter,
        console_export=False,
    )


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
        call_id: str,
        agent_number: str,
        provider: str,
        call_direction: str,
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
            'region': tts_config.get('region'),
            'voice_id': default_voice_id,  # Will be overridden per language in multi-lang mode
            'parameters': tts_parameters or {},
        }

        # Merge STT config credentials with agent's parameters
        stt_config_with_params = {
            'provider': stt_config['provider'],
            'api_key': stt_config['api_key'],
            'region': stt_config.get('region'),
            'parameters': stt_parameters or {},
        }

        if is_multi_language:
            logger.info(
                f'Multi-language mode enabled for languages: {supported_languages}. '
                f'Creating single TTS/STT service with default language: {default_language}'
            )

            # Create a single TTS service with the default language; language switches
            # are handled at runtime via TTSUpdateSettingsFrame / STTUpdateSettingsFrame
            tts_config_lang = deepcopy(tts_config_with_params)
            if 'parameters' not in tts_config_lang:
                tts_config_lang['parameters'] = {}
            tts_config_lang['parameters']['language'] = default_language
            tts_config_lang['voice_id'] = tts_voice_ids_dict.get(
                default_language, default_voice_id
            )
            tts = TTSServiceFactory.create_tts_service(tts_config_lang)

            stt_config_lang = deepcopy(stt_config_with_params)
            if 'parameters' not in stt_config_lang:
                stt_config_lang['parameters'] = {}
            stt_config_lang['parameters']['language'] = default_language
            stt = STTServiceFactory.create_stt_service(stt_config_lang)

        else:
            logger.info('Single language mode - no language detection needed')

            # Create single STT/TTS services using merged configs
            stt = STTServiceFactory.create_stt_service(stt_config_with_params)
            tts = TTSServiceFactory.create_tts_service(tts_config_with_params)

        # Create initial messages with system prompt
        base_system_prompt = (
            f'Customer phone number: {customer_number}\n'
            f'{get_current_ist_time_str()}\n' + agent_config['system_prompt']
        )

        # Add language instruction for default language if multi-language
        if is_multi_language:
            initial_language_instruction = LANGUAGE_INSTRUCTIONS.get(
                default_language, LANGUAGE_INSTRUCTIONS.get('en', 'Respond in English.')
            )
            supported_language_names = [
                LANGUAGE_DISPLAY_NAMES.get(code, code) for code in supported_languages
            ]
            language_switching_rules = (
                f'\n\nLANGUAGE SWITCHING RULES (follow exactly, no exceptions):\n'
                f'Supported languages: {", ".join(supported_language_names)}.\n'
                f'Current language: {LANGUAGE_DISPLAY_NAMES.get(default_language, default_language)}.\n\n'
                f'CASE 1 — USER WANTS THE ASSISTANT TO USE A DIFFERENT LANGUAGE:\n'
                f'The user is asking or implying that they want the conversation to happen in a specific supported language. Triggers include:\n'
                f'  - Saying a supported language name alone (e.g. "Hindi", "English", "Tamil")\n'
                f'  - Asking if you can speak/use a language (e.g. "Can you speak in English?", "क्या आप हिंदी में बात कर सकते हैं?")\n'
                f'  - Requesting a switch (e.g. "switch to Hindi", "speak in Tamil", "Hindi mein baat karo", "change language")\n'
                f'  - Saying "speaking [language]" implying they want the assistant to speak it (e.g. "Speaking Hindi")\n'
                f'  - Responding with a language name after being asked which language they want\n'
                f'  - A word that phonetically resembles a supported language name — STT often mishears language names '
                f'(e.g. "Hindi" → "Indy" or "Indie", "Kannada" → "Canada", "Telugu" → "Tell you"). '
                f'Use phonetic judgment: if the word sounds like a supported language name in context, treat it as CASE 1.\n'
                f'BIAS RULE: When in doubt between CASE 1 and CASE 2, if a supported language name (or phonetic match) '
                f'appears in the message, default to CASE 1.\n'
                f'ACTION: Call detect_and_switch_language immediately. Do NOT ask for confirmation. Do NOT say anything before calling the tool.\n\n'
                f'CASE 2 — USER SPEAKS IN A DIFFERENT LANGUAGE (no language name mentioned, no switch request):\n'
                f'The user sends a full message in a language different from the current language, '
                f'with NO mention of a language name and NO request to switch. They are just talking.\n'
                f'NOTE: STT may transcribe foreign speech phonetically in the current language script — '
                f'e.g. if current language is English and the user speaks Hindi, STT may output romanized Hindi '
                f'like "Ha muje naye loan ke baare mai batao". Recognize this as Hindi input, not English.\n'
                f'ACTION: Do NOT call detect_and_switch_language. Do NOT answer their query. '
                f'Respond in the CURRENT language (the language you are currently configured to speak) with this meaning: '
                f'"Are you trying to switch the language? If yes, please say one of: {", ".join(supported_language_names)}"\n\n'
                f'CASE 3 — UNSUPPORTED LANGUAGE REQUESTED:\n'
                f'The user requests a language not in the supported list.\n'
                f'ACTION: Do NOT call detect_and_switch_language. Inform the user that only these languages are supported: '
                f'{", ".join(supported_language_names)}.\n\n'
                f'CRITICAL RULES:\n'
                f'- Never call detect_and_switch_language for Case 2 or Case 3.\n'
                f'- Never answer a query in the wrong language before switching.\n'
                f'- Never ask for confirmation before switching in Case 1.\n'
                f'- Never respond with your own words before or instead of calling the tool in Case 1.\n'
                f'- Never invent responses outside these three cases.'
            )
            system_content = f'{initial_language_instruction}\n\n{base_system_prompt}{language_switching_rules}'
            # Store base prompt without language instruction for switching (rules persist across switches)
            language_state['original_system_prompt'] = (
                base_system_prompt + language_switching_rules
            )
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
                    tts_provider=tts_config['provider'],
                    stt_provider=stt_config['provider'],
                    tts_voice_ids=tts_voice_ids_dict,
                    context_container=context_container,
                    supported_languages=supported_languages,
                    default_language=default_language,
                    language_state=language_state,
                )
            )

            llm.register_function('detect_and_switch_language', language_detection_func)
            logger.info('Registered language detection tool with LLM')

        # Register conversation completion tool
        # conversation_completion_func = (
        #     ConversationCompletionToolFactory.create_conversation_completion_tool(
        #         task_container=task_container
        #     )
        # )
        # llm.register_function('end_conversation', conversation_completion_func)
        logger.info('Registered conversation completion tool with LLM')

        # Create FunctionSchema for conversation completion
        # end_conversation_schema = FunctionSchema(
        #     name='end_conversation',
        #     description=(
        #         'Call this function when the user indicates they want to end the conversation. '
        #         'This includes goodbye phrases, expressions of completion, or any indication '
        #         'that the user wants to hang up or finish the call. Examples: "goodbye", "bye", '
        #         '"thank you", "that\'s all", "I\'m done", etc.'
        #     ),
        #     properties={
        #         'farewell_message': {
        #             'type': 'string',
        #             'description': (
        #                 'Optional custom farewell message to say to the user before ending. '
        #                 'If not provided, uses default: "Thank you for using our service! Goodbye!"'
        #             ),
        #         }
        #     },
        #     required=[],
        # )

        # Create FunctionSchema for language detection (if multi-language)
        language_detection_schemas = []
        if is_multi_language:
            language_detection_schema = FunctionSchema(
                name='detect_and_switch_language',
                description=(
                    f"Switch the conversation language. "
                    f"Call this when the user wants the assistant to use a specific language — "
                    f"this includes: saying a language name directly ('Hindi', 'Tamil'), "
                    f"asking 'can you speak in X?', saying 'speaking [language]', "
                    f"or phrases like 'switch to Hindi', 'speak in Tamil', 'Hindi mein baat karo'. "
                    f"STT may mishear language names (e.g. 'Hindi' → 'Indy', 'Kannada' → 'Canada') — use phonetic judgment. "
                    f"When in doubt and a language name is present, call this tool. "
                    f"Do NOT call this tool when the user simply starts speaking in another language with no language name and no switch request — "
                    f"in that case respond in the current language asking if they want to switch. "
                    f"Only switch to supported languages: {', '.join(supported_language_names)}. "
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
            # [end_conversation_schema] +
            language_detection_schemas + function_schemas
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
                    MuteUntilFirstBotCompleteUserMuteStrategy(),
                    FunctionCallUserMuteStrategy(),
                ],
            ),
        )

        # --- Call evaluation: transcript log and stats ---
        transcript_log: List[Dict[str, Any]] = []
        call_evaluation_tasks: List[asyncio.Task] = []
        call_stats: Dict[str, Any] = {
            'user_turns': 0,
            'assistant_turns': 0,
            'interruption_count': 0,
            'tool_calls_count': 0,
            'language_switch_count': 0,
            '_bot_speaking': False,
        }

        @context_aggregator.user().event_handler('on_user_turn_started')
        async def on_user_turn_started(aggregator, strategy):
            if call_stats['_bot_speaking']:
                call_stats['interruption_count'] += 1

        @context_aggregator.user().event_handler('on_user_turn_stopped')
        async def on_user_turn_stopped(
            aggregator, strategy, message: UserTurnStoppedMessage
        ):
            call_stats['user_turns'] += 1
            transcript_log.append(
                {
                    'role': 'user',
                    'content': message.content,
                    'timestamp': message.timestamp,
                }
            )

        @context_aggregator.assistant().event_handler('on_assistant_turn_started')
        async def on_assistant_turn_started(aggregator):
            call_stats['_bot_speaking'] = True

        @context_aggregator.assistant().event_handler('on_assistant_turn_stopped')
        async def on_assistant_turn_stopped(
            aggregator, message: AssistantTurnStoppedMessage
        ):
            call_stats['_bot_speaking'] = False
            call_stats['assistant_turns'] += 1
            transcript_log.append(
                {
                    'role': 'assistant',
                    'content': message.content,
                    'timestamp': message.timestamp,
                }
            )

        # Build pipeline components list
        pipeline_components = [
            transport.input(),  # Audio input from Twilio
            stt,  # Speech-to-Text
            context_aggregator.user(),  # Add user message to context
            llm,  # LLM processing
            tts,  # Text-to-Speech
            transport.output(),  # Audio output to Twilio
            context_aggregator.assistant(),  # Add assistant response to context
        ]

        # Create pipeline
        pipeline = Pipeline(pipeline_components)

        # Mask customer number: keep last 4 digits
        masked_customer_number = (
            '*' * (len(customer_number) - 4) + customer_number[-4:]
            if customer_number and len(customer_number) > 4
            else customer_number
        )

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
            idle_timeout_frames=(
                BotSpeakingFrame,
                UserSpeakingFrame,
                BotStartedSpeakingFrame,
                UserStartedSpeakingFrame,
            ),
            idle_timeout_secs=300,
            enable_tracing=ENABLE_TRACING,
            enable_turn_tracking=ENABLE_TURN_TRACKING,
            conversation_id=None,
            additional_span_attributes={
                'customer.phone_number': masked_customer_number,
                'voice_agent.id': str(agent_id) if agent_id else '',
                'voice_agent.name': agent_config.get('name', ''),
                'call.direction': call_direction,
                'call.id': call_id,
                'telephony.provider': provider,
                'telephony.agent_number': agent_number,
            },
        )

        # Populate task container for language detection tool (if multi-language)
        task_container['task'] = task

        # Register event handlers
        @llm.event_handler('on_function_calls_started')
        async def on_function_calls_started(service, function_calls):
            if (
                os.getenv('ENABLE_FILLER_PHRASES_BEFORE_TOOL_CALL', '').lower()
                != 'true'
            ):
                return
            # Skip filler phrase when language is switching — the TTS service's language
            # may change before the queued frame is processed, causing a language mismatch error.
            call_names = [fc.function_name for fc in function_calls]
            if 'detect_and_switch_language' in call_names:
                return
            # Count non-language-switch tool invocations
            call_stats['tool_calls_count'] += len(function_calls)
            current_lang = language_state.get('current_language', 'en')
            phrases = FILLER_PHRASES.get(current_lang)
            if not phrases:
                return
            phrase = random.choice(phrases)
            await task.queue_frame(TTSSpeakFrame(phrase))

        @task.event_handler('on_pipeline_finished')
        async def on_pipeline_finished(task, frame):
            if isinstance(frame, EndFrame):
                outcome = 'completed'
            elif isinstance(frame, CancelFrame):
                outcome = 'cancelled'
            elif isinstance(frame, ErrorFrame):
                outcome = 'error'
            elif isinstance(frame, StopFrame):
                outcome = 'stopped'
            else:
                outcome = 'unknown'
            # Pull language switch count from language_state (already tracked there)
            call_stats['language_switch_count'] = language_state.get('switch_count', 0)
            if ENABLE_TRACING and OTLP_ENDPOINT:
                # Capture the current OTel context now, while the pipecat span is still
                # active. The background task will use this as the parent so call.evaluation
                # appears under the same trace rather than as a new root trace.
                parent_ctx = otel_context.get_current()
                t = asyncio.create_task(
                    CallEvaluationService.record_call_metrics(
                        call_id=call_id,
                        agent_config=agent_config,
                        call_outcome=outcome,
                        transcript_log=transcript_log,
                        stats=call_stats,
                        parent_context=parent_ctx,
                    )
                )
                call_evaluation_tasks.append(t)

        @transport.event_handler('on_client_connected')
        async def on_client_connected(transport, client):
            logger.info(f"Client connected for agent: {agent_config['name']}")
            await task.queue_frame(
                TTSSpeakFrame(agent_config['welcome_message'], append_to_context=True)
            )

        @transport.event_handler('on_client_disconnected')
        async def on_client_disconnected(transport, client):
            logger.info(f"Client disconnected for agent: {agent_config['name']}")
            await task.cancel()

        # Run pipeline
        runner = PipelineRunner(handle_sigint=False)
        try:
            await runner.run(task)
        except Exception as e:
            logger.error(
                f"Pipeline error for agent {agent_config['name']}: {e}",
                exc_info=True,
            )
            raise
        finally:
            await task.cancel()
            if call_evaluation_tasks:
                await asyncio.gather(*call_evaluation_tasks, return_exceptions=True)
            logger.info(f"Conversation ended for agent: {agent_config['name']}")
