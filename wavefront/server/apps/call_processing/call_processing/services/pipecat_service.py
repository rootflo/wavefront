"""
Pipecat pipeline orchestration service

Creates and runs the voice conversation pipeline using configured STT/LLM/TTS services
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat core imports
from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.transports.base_transport import BaseTransport

from call_processing.services.stt_service import STTServiceFactory
from call_processing.services.tts_service import TTSServiceFactory
from call_processing.services.llm_service import LLMServiceFactory


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

        # Create LLM context and aggregator
        context = LLMContext(messages)
        context_aggregator = LLMContextAggregatorPair(context)

        # Create pipeline
        pipeline = Pipeline(
            [
                transport.input(),  # Audio input from Twilio
                stt,  # Speech-to-Text
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
            idle_timeout_secs=12,
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
