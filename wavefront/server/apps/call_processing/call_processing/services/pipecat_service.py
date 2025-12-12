"""
Pipecat pipeline orchestration service

Creates and runs the voice conversation pipeline using configured STT/LLM/TTS services
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat core imports
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.frames.frames import TTSSpeakFrame, EndTaskFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.transports.base_transport import BaseTransport
from pipecat.services.llm_service import FunctionCallParams
from call_processing.services.stt_service import STTServiceFactory
from call_processing.services.tts_service import TTSServiceFactory
from call_processing.services.llm_service import LLMServiceFactory


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


user_idle = UserIdleProcessor(
    callback=handle_user_idle,  # Your callback function
    timeout=4.0,  # Seconds of inactivity before triggering
)


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
    ):
        """
        Create and run the Pipecat pipeline for a voice conversation

        Args:
            transport: Pipecat transport (e.g., WebSocket transport from Twilio)
            agent_config: Voice agent configuration including system_prompt
            llm_config: LLM provider configuration
            tts_config: TTS provider configuration
            stt_config: STT provider configuration
        """
        logger.info(f"Starting conversation for agent: {agent_config['name']}")

        # Create services using factories
        stt = STTServiceFactory.create_stt_service(stt_config)
        llm = LLMServiceFactory.create_llm_service(llm_config)
        tts = TTSServiceFactory.create_tts_service(tts_config)

        # Create initial messages with system prompt
        messages = [
            {
                'role': 'system',
                'content': agent_config['system_prompt'],
            }
        ]

        # ADD: Register function handler with LLM service
        llm.register_function(
            'check_conversation_complete', check_conversation_complete
        )

        tools = ToolsSchema(standard_tools=[check_conversation_complete])
        # Create LLM context and aggregator
        context = LLMContext(messages, tools=tools)
        context_aggregator = LLMContextAggregatorPair(context)

        # Create pipeline
        pipeline = Pipeline(
            [
                transport.input(),  # Audio input from Twilio
                stt,  # Speech-to-Text
                user_idle,
                context_aggregator.user(),  # Add user message to context
                llm,  # LLM processing
                tts,  # Text-to-Speech
                transport.output(),  # Audio output to Twilio
                context_aggregator.assistant(),  # Add assistant response to context
            ]
        )

        # Create pipeline task with Twilio-specific parameters
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,  # Twilio uses 8kHz
                audio_out_sample_rate=8000,
                enable_metrics=True,
                # enable_usage_metrics=True,
                allow_interruptions=True,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=2)],
                # report_only_initial_ttfb=True
            ),
            idle_timeout_secs=20,  # Safety net - allows UserIdleProcessor to complete 3 retries (4s each = 12s total)
        )

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
