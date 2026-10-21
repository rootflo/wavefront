"""Build the per-agent part of a voice pipeline (``AgentStack``).

Shared by the telephony and browser (WebRTC) flows; what differs between them
is passed in as ``StackOptions``.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from call_processing.constants.language_config import LANGUAGE_DISPLAY_NAMES
from call_processing.log.logger import logger
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.common.audio_config import with_sample_rate
from call_processing.services.common.filler_speech import (
    FillerSpeechConfig,
    FillerSpeechProcessor,
)
from call_processing.services.common.prompts import (
    END_CONVERSATION_DESCRIPTION,
    END_CONVERSATION_FAREWELL_DESCRIPTION,
    LANGUAGE_TOOL_INTENT_DESCRIPTION,
    language_instruction,
    language_switching_rules,
    language_tool_description,
    language_tool_target_description,
)
from call_processing.services.common.providers.llm_service import LLMServiceFactory
from call_processing.services.common.providers.stt_service import STTServiceFactory
from call_processing.services.common.providers.tts_service import TTSServiceFactory
from call_processing.services.common.session_events import (
    STATE_LISTENING,
    STATE_SPEAKING,
    STATE_THINKING,
)
from call_processing.services.common.tools.conversation_completion_tool import (
    ConversationCompletionToolFactory,
    EndConversationConfig,
)
from call_processing.services.common.tools.language_detection_tool import (
    LanguageDetectionToolFactory,
)
from call_processing.services.common.tools.tool_wrapper_service import (
    ToolWrapperFactory,
)
from call_processing.services.common.turn_taking import TurnTakingConfig


@dataclass(frozen=True)
class StackOptions:
    """How a flow builds its agent stacks (the same for every stack of a call)."""

    # Forced onto STT/TTS (browser audio is wideband); None keeps the 8 kHz
    # telephony service defaults
    service_sample_rate: Optional[int] = None
    # Per-call context appended to the system prompt (telephony caller details).
    # It goes at the very end: the static part before it stays a stable prefix
    # the provider can prompt-cache across calls.
    prompt_suffix: str = ''
    # Browser rooms: the app drives the language via ``set_context.language``,
    # so a multi-language agent gets no language instruction prefix, no
    # LANGUAGE SWITCHING RULES and no ``detect_and_switch_language`` tool.
    # STT/TTS are still multi-language.
    room_context_language: bool = False


def build_agent_stack(
    *,
    agent_config: Dict[str, Any],
    llm_config: Dict[str, Any],
    tts_config: Dict[str, Any],
    stt_config: Dict[str, Any],
    tools: List[Dict[str, Any]],
    shared: SharedSession,
    options: StackOptions,
    is_initial_stack: bool = True,
) -> AgentStack:
    """Build everything that belongs to a single agent.

    STT/LLM/TTS services, system prompt and language rules, tools, conversation
    context and its aggregators. Call-level state (stats, transcript, task,
    client events) comes from ``shared`` so a stack can be built off to the side
    and swapped into a running session.
    """
    call_stats = shared.call_stats
    transcript_log = shared.transcript_log

    # Extract language configuration from agent_config
    supported_languages = agent_config.get('supported_languages', ['en'])
    default_language = agent_config.get('default_language', 'en')
    is_multi_language = len(supported_languages) > 1
    # The model-driven language tool and its prompt rules (native approach)
    use_language_tool = is_multi_language and not options.room_context_language

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
    language_state: Dict[str, Any] = {
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

    stt_config_with_params = with_sample_rate(
        stt_config_with_params, options.service_sample_rate
    )
    tts_config_with_params = with_sample_rate(
        tts_config_with_params, options.service_sample_rate
    )
    logger.info(
        f"Audio sample rates: "
        f"stt={stt_config_with_params['parameters'].get('sample_rate', 'service default')}, "
        f"tts={tts_config_with_params['parameters'].get('sample_rate', 'pipeline rate')}"
    )

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

    call_context = options.prompt_suffix
    base_system_prompt = agent_config['system_prompt']

    supported_language_names = [
        LANGUAGE_DISPLAY_NAMES.get(code, code) for code in supported_languages
    ]

    # Add language instruction for default language if multi-language
    if is_multi_language and options.room_context_language:
        # The app sets the language through the step overlay; keep the prompt
        # exactly as the agent author wrote it.
        system_content = base_system_prompt + call_context
        # Non-empty marks the agent as multi-language for the browser messenger
        language_state['original_system_prompt'] = system_content
    elif is_multi_language:
        language_rules = language_switching_rules(
            supported_language_names,
            LANGUAGE_DISPLAY_NAMES.get(default_language, default_language),
        )
        system_content = f'{language_instruction(default_language)}\n\n{base_system_prompt}{language_rules}{call_context}'
        # Store base prompt without language instruction for switching (rules persist across switches)
        language_state['original_system_prompt'] = (
            base_system_prompt + language_rules + call_context
        )
    else:
        system_content = base_system_prompt + call_context

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
            ) = ToolWrapperFactory.create_all_tool_functions(
                tools,
                # App tools talk to the browser; it only exists once the pipeline
                # is built, so they look the messenger up when called.
                messenger_getter=lambda: shared.messenger,
            )

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

    # Late-binding containers: the task is shared by all stacks and set once it
    # exists; the context belongs to this stack.
    task_container = shared.task_container
    context_container = {'context': None}

    # Conversation completion tool (farewell TTS then EndFrame): opt-in per
    # agent, so by default the bot never ends the call on its own.
    end_conversation_config = EndConversationConfig.from_agent_config(agent_config)
    end_conversation_schemas = []
    if end_conversation_config.enabled:
        llm.register_function(
            'end_conversation',
            ConversationCompletionToolFactory.create_conversation_completion_tool(
                task_container=task_container,
                default_farewell=end_conversation_config.farewell_message,
            ),
        )
        logger.info('Registered conversation completion tool with LLM')
        end_conversation_schemas.append(
            FunctionSchema(
                name='end_conversation',
                description=END_CONVERSATION_DESCRIPTION,
                properties={
                    'farewell_message': {
                        'type': 'string',
                        'description': END_CONVERSATION_FAREWELL_DESCRIPTION,
                    }
                },
                required=[],
            )
        )

    # Language detection tool (native approach only)
    language_detection_schemas = []
    if use_language_tool:
        llm.register_function(
            'detect_and_switch_language',
            LanguageDetectionToolFactory.create_language_detection_tool(
                task_container=task_container,
                tts_provider=tts_config['provider'],
                stt_provider=stt_config['provider'],
                tts_voice_ids=tts_voice_ids_dict,
                context_container=context_container,
                supported_languages=supported_languages,
                default_language=default_language,
                language_state=language_state,
                # Browser sessions: tell the app which language the agent settled on
                on_language_selected=lambda language: (
                    shared.events.emit_language_changed(language)
                ),
            ),
        )
        logger.info('Registered language detection tool with LLM')
        language_detection_schemas.append(
            FunctionSchema(
                name='detect_and_switch_language',
                description=language_tool_description(
                    supported_language_names, language_state['current_language']
                ),
                properties={
                    'target_language': {
                        'type': 'string',
                        'description': language_tool_target_description(
                            supported_languages
                        ),
                        'enum': supported_languages,
                    },
                    'user_intent': {
                        'type': 'string',
                        'description': LANGUAGE_TOOL_INTENT_DESCRIPTION,
                    },
                },
                required=['target_language', 'user_intent'],
            )
        )

    # Combine all FunctionSchema objects for ToolsSchema
    all_function_schemas = (
        end_conversation_schemas + language_detection_schemas + function_schemas
    )
    tools_schema = ToolsSchema(standard_tools=all_function_schemas)

    # Create LLM context and aggregator
    context = LLMContext(messages, tools=tools_schema)

    # Populate context container for language detection tool (if registered)
    if use_language_tool:
        context_container['context'] = context

    # VAD must live on the user aggregator in Pipecat 1.x — TransportParams
    # no longer accepts vad_analyzer (silently dropped), which would leave
    # VADUserTurnStartStrategy with nothing to drive turn starts.
    # Turn-taking and filler timing are per agent (conversation_config).
    turn_taking = TurnTakingConfig.from_agent_config(agent_config)
    # The welcome is only spoken at connect, i.e. by the call's first agent
    will_greet = is_initial_stack and bool(
        (agent_config.get('welcome_message') or '').strip()
    )
    if turn_taking.mute_until_first_bot_complete and not will_greet:
        logger.info(
            'mute_until_first_bot_complete ignored: no welcome message to wait for'
        )
    filler_config = FillerSpeechConfig.from_agent_config(agent_config)
    filler = FillerSpeechProcessor(delay_secs=filler_config.thinking_delay_secs)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=turn_taking.vad_params()),
            user_turn_strategies=UserTurnStrategies(
                start=turn_taking.start_strategies(),
                stop=turn_taking.stop_strategies(),
            ),
            user_mute_strategies=turn_taking.mute_strategies(will_greet=will_greet),
        ),
    )

    agent_id_tag = str(agent_id) if agent_id else ''

    @context_aggregator.user().event_handler('on_user_turn_started')
    async def on_user_turn_started(aggregator, strategy):
        await filler.cancel_thinking_filler()
        if call_stats['_bot_speaking']:
            call_stats['interruption_count'] += 1
        await shared.events.emit_agent_state(STATE_LISTENING)

    @context_aggregator.user().event_handler('on_user_turn_stopped')
    async def on_user_turn_stopped(
        aggregator, strategy, message: UserTurnStoppedMessage
    ):
        call_stats['user_turns'] += 1
        transcript_log.append(
            {
                'role': 'user',
                'agent_id': agent_id_tag,
                'content': message.content,
                'timestamp': message.timestamp,
            }
        )
        await shared.events.emit_transcript(message.content)
        await shared.events.emit_agent_state(STATE_THINKING)
        # Backchannel only if the LLM is slow to start (see FillerSpeechProcessor)
        if filler_config.thinking:
            await filler.arm_thinking_filler(
                filler_config.thinking_phrases_for(
                    language_state.get('current_language', 'en')
                )
            )

    @context_aggregator.assistant().event_handler('on_assistant_turn_started')
    async def on_assistant_turn_started(aggregator):
        call_stats['_bot_speaking'] = True
        await shared.events.emit_agent_state(STATE_SPEAKING)

    @context_aggregator.assistant().event_handler('on_assistant_turn_stopped')
    async def on_assistant_turn_stopped(
        aggregator, message: AssistantTurnStoppedMessage
    ):
        call_stats['_bot_speaking'] = False
        call_stats['assistant_turns'] += 1
        await shared.events.emit_agent_state(STATE_LISTENING)
        transcript_log.append(
            {
                'role': 'assistant',
                'agent_id': agent_id_tag,
                'content': message.content,
                'timestamp': message.timestamp,
            }
        )

    @llm.event_handler('on_function_calls_started')
    async def on_function_calls_started(service, function_calls):
        call_names = {fc.function_name for fc in function_calls}
        # Language switches are not tool work the caller is waiting on
        call_stats['tool_calls_count'] += len(
            call_names - {'detect_and_switch_language'}
        )
        if not filler_config.before_tool_call:
            return
        # No filler around a language switch (the TTS language may change
        # before it is spoken) or before the goodbye ("One moment... Goodbye!").
        if call_names & {'detect_and_switch_language', 'end_conversation'}:
            return
        await filler.speak_one_of(
            filler_config.tool_call_phrases_for(
                language_state.get('current_language', 'en')
            )
        )

    return AgentStack(
        agent_config=agent_config,
        stt=stt,
        llm=llm,
        tts=tts,
        context=context,
        context_aggregator=context_aggregator,
        language_state=language_state,
        function_schemas=all_function_schemas,
        supported_languages=supported_languages if is_multi_language else [],
        tts_provider=tts_config['provider'],
        stt_provider=stt_config['provider'],
        tts_voice_ids=tts_voice_ids_dict,
        welcome_message=(agent_config.get('welcome_message') or '').strip(),
        filler=filler,
    )
