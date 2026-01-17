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
from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.frames.frames import (
    TTSSpeakFrame,
    EndTaskFrame,
    ManuallySwitchServiceFrame,
    LLMMessagesUpdateFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.processors.transcript_processor import (
    TranscriptProcessor,
    TranscriptionMessage,
)
from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyManual,
)
from pipecat.transports.base_transport import BaseTransport
from pipecat.services.llm_service import FunctionCallParams
from call_processing.services.stt_service import STTServiceFactory
from call_processing.services.tts_service import TTSServiceFactory
from call_processing.services.llm_service import LLMServiceFactory
from call_processing.constants.language_config import (
    LANGUAGE_KEYWORDS,
    LANGUAGE_INSTRUCTIONS,
)


# Advanced handler with retry logic
async def handle_user_idle(processor: FrameProcessor, retry_count):
    if retry_count == 1:
        # First attempt - gentle reminder
        await processor.push_frame(TTSSpeakFrame('Are you still there?'))
        return True  # Continue monitoring
    elif retry_count == 2:
        # Second attempt - more direct prompt
        await processor.push_frame(
            TTSSpeakFrame('Would you like to continue our conversation?')
        )
        return True  # Continue monitoring
    else:
        # Third attempt - end conversation
        await processor.push_frame(
            TTSSpeakFrame("I'll leave you for now. Have a nice day!")
        )
        await processor.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
        return False  # Stop monitoring


async def evaluate_completion_criteria(params: FunctionCallParams):
    """
    Check if the last user message contains goodbye-related phrases.
    Returns True if goodbye detected, False otherwise.
    """
    context = params.context

    # Get the conversation messages
    messages = context.get_messages()

    # Find the last user message
    last_user_message = None
    for message in reversed(messages):
        if message.get('role') == 'user':
            last_user_message = message.get('content', '').lower()
            break

    # If no user message found, conversation is not complete
    if not last_user_message:
        return False

    # List of goodbye phrases to check
    goodbye_phrases = [
        'goodbye',
        'bye',
        'good bye',
        'see you',
        'talk to you later',
        'ttyl',
        'have a good day',
        'take care',
        'farewell',
        'later',
        'peace out',
    ]

    # Check if any goodbye phrase is in the message
    return any(phrase in last_user_message for phrase in goodbye_phrases)


async def check_conversation_complete(params: FunctionCallParams):
    """
    Function to check if conversation should end based on goodbye detection.
    """
    # Check if goodbye is present
    conversation_complete = await evaluate_completion_criteria(params)

    if conversation_complete:
        # Send farewell message
        await params.llm.push_frame(
            TTSSpeakFrame('Thank you for using our service! Goodbye!')
        )
        # End the conversation
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    # Return result to LLM
    await params.result_callback(
        {
            'status': 'complete' if conversation_complete else 'continuing',
            'goodbye_detected': conversation_complete,
        }
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
        tts_voice_id = agent_config.get('tts_voice_id')
        tts_parameters = agent_config.get('tts_parameters', {})
        stt_parameters = agent_config.get('stt_parameters', {})

        logger.info(f"Starting conversation for agent: {agent_config['name']}")
        logger.info(
            f'Language config - supported: {supported_languages}, '
            f'default: {default_language}, multi-language: {is_multi_language}'
        )

        # Create LLM service (language-agnostic)
        llm = LLMServiceFactory.create_llm_service(llm_config)

        # Merge TTS config credentials with agent's voice and parameters
        tts_config_with_params = {
            'provider': tts_config['provider'],
            'api_key': tts_config['api_key'],
            'voice_id': tts_voice_id,
            'parameters': tts_parameters or {},
        }

        # Merge STT config credentials with agent's parameters
        stt_config_with_params = {
            'provider': stt_config['provider'],
            'api_key': stt_config['api_key'],
            'parameters': stt_parameters or {},
        }

        # Create STT/TTS services with multi-language support if needed
        stt_services = {}
        tts_services = {}

        if is_multi_language:
            logger.info(
                f'Multi-language mode enabled for languages: {supported_languages}'
            )

            # Create STT/TTS services for each supported language
            for lang_code in supported_languages:
                # Deep clone configs to avoid mutating original configs
                stt_config_lang = deepcopy(stt_config_with_params)
                tts_config_lang = deepcopy(tts_config_with_params)

                # Update language in parameters
                if 'parameters' not in stt_config_lang:
                    stt_config_lang['parameters'] = {}
                stt_config_lang['parameters']['language'] = lang_code

                if 'parameters' not in tts_config_lang:
                    tts_config_lang['parameters'] = {}
                tts_config_lang['parameters']['language'] = lang_code

                # Create services
                stt_services[lang_code] = STTServiceFactory.create_stt_service(
                    stt_config_lang
                )
                tts_services[lang_code] = TTSServiceFactory.create_tts_service(
                    tts_config_lang
                )

                logger.info(f'Created STT/TTS services for language: {lang_code}')

            # Create service switchers with manual strategy
            # Order services list with default language first (ServiceSwitcher uses first as initial)
            stt_services_list = []
            tts_services_list = []

            # Add default language service first
            if default_language in stt_services:
                stt_services_list.append(stt_services[default_language])
                tts_services_list.append(tts_services[default_language])

            # Add remaining services
            for lang_code in supported_languages:
                if lang_code != default_language:
                    stt_services_list.append(stt_services[lang_code])
                    tts_services_list.append(tts_services[lang_code])

            stt = ServiceSwitcher(
                services=stt_services_list, strategy_type=ServiceSwitcherStrategyManual
            )
            tts = ServiceSwitcher(
                services=tts_services_list, strategy_type=ServiceSwitcherStrategyManual
            )

            logger.info(f'Initialized with default language: {default_language}')
        else:
            logger.info('Single language mode - no language detection needed')

            # Create single STT/TTS services using merged configs
            stt = STTServiceFactory.create_stt_service(stt_config_with_params)
            tts = TTSServiceFactory.create_tts_service(tts_config_with_params)

        # Create initial messages with system prompt
        messages = [
            {
                'role': 'system',
                'content': agent_config['system_prompt'],
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

        # Register built-in function handler with LLM service
        llm.register_function(
            'check_conversation_complete', check_conversation_complete
        )

        # Create FunctionSchema for check_conversation_complete
        check_complete_schema = FunctionSchema(
            name='check_conversation_complete',
            description='Check if conversation should end based on goodbye detection',
            properties={},  # No parameters needed
            required=[],
        )

        # Combine all FunctionSchema objects for ToolsSchema
        all_function_schemas = [check_complete_schema] + function_schemas
        tools_schema = ToolsSchema(standard_tools=all_function_schemas)

        # Create LLM context and aggregator
        context = LLMContext(messages, tools=tools_schema)
        context_aggregator = LLMContextAggregatorPair(context)

        # Create transcript processor for language detection
        transcript = TranscriptProcessor()

        # Track current language detection state (only for multi-language)
        language_detected = {'detected': False, 'current_language': default_language}

        # Create user idle processor (fresh instance for each conversation)
        user_idle = UserIdleProcessor(
            callback=handle_user_idle,
            timeout=4.0,
        )

        # Build pipeline components list
        pipeline_components = [
            transport.input(),  # Audio input from Twilio
            stt,  # Speech-to-Text (ServiceSwitcher for multi-lang, direct for single)
            transcript.user(),  # Transcript processor for user messages
            user_idle,  # User idle detection
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
                allow_interruptions=True,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=3)],
                # report_only_initial_ttfb=True
            ),
            idle_timeout_secs=20,  # Safety net - allows UserIdleProcessor to complete 3 retries (4s each = 12s total)
        )

        # Multi-language detection event handler
        if is_multi_language:

            @transcript.event_handler('on_transcript_update')
            async def handle_language_detection(processor, frame):
                """Detect language from first user message and switch services"""

                # Only detect once
                if language_detected['detected']:
                    return

                messages: List[TranscriptionMessage] = frame.messages

                # Look for user messages
                for message in messages:
                    if message.role == 'user':
                        message_content = message.content.lower().strip()

                        # Skip empty messages
                        if not message_content:
                            continue

                        logger.info(
                            f"Analyzing message for language detection: '{message_content}'"
                        )

                        # Check for language keywords
                        detected_lang = None
                        for lang_code in supported_languages:
                            keywords = LANGUAGE_KEYWORDS.get(lang_code, [])
                            for keyword in keywords:
                                if keyword.lower() in message_content:
                                    detected_lang = lang_code
                                    logger.info(
                                        f'Language detected: {detected_lang} '
                                        f"(matched keyword: '{keyword}')"
                                    )
                                    break
                            if detected_lang:
                                break

                        # Use detected language or fallback to default
                        target_language = detected_lang or default_language

                        if not detected_lang:
                            logger.info(
                                f'No language detected, using default: {default_language}'
                            )

                        # Mark detection as complete
                        language_detected['detected'] = True
                        language_detected['current_language'] = target_language

                        # Only switch services if target language is different from default
                        if target_language != default_language:
                            if (
                                target_language in stt_services
                                and target_language in tts_services
                            ):
                                target_stt = stt_services[target_language]
                                target_tts = tts_services[target_language]

                                try:
                                    await task.queue_frames(
                                        [
                                            ManuallySwitchServiceFrame(
                                                service=target_stt
                                            ),
                                            ManuallySwitchServiceFrame(
                                                service=target_tts
                                            ),
                                        ]
                                    )
                                    logger.info(
                                        f'Switched STT/TTS services to language: {target_language}'
                                    )
                                except Exception as e:
                                    logger.error(
                                        f'Error switching services: {e}', exc_info=True
                                    )
                        else:
                            logger.info(
                                f'Language {target_language} is default, no service switch needed'
                            )

                        # Update LLM system prompt with language instruction
                        language_instruction = LANGUAGE_INSTRUCTIONS.get(
                            target_language,
                            LANGUAGE_INSTRUCTIONS.get('en', 'Respond in English.'),
                        )

                        # Get current system prompt and append language instruction
                        current_messages = context.get_messages()
                        if current_messages and len(current_messages) > 0:
                            system_message = current_messages[0]
                        else:
                            system_message = {
                                'role': 'system',
                                'content': agent_config['system_prompt'],
                            }

                        updated_content = (
                            f"{system_message['content']}\n\n{language_instruction}"
                        )
                        updated_system_message = {
                            'role': 'system',
                            'content': updated_content,
                        }

                        # Update context with new system message
                        new_messages = [updated_system_message] + current_messages[1:]
                        await task.queue_frame(
                            LLMMessagesUpdateFrame(new_messages, run_llm=False)
                        )

                        logger.info(
                            f'Updated LLM context with language instruction for {target_language}'
                        )

                        # Exit after first detection
                        break

            logger.info('Language detection event handler registered')

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
