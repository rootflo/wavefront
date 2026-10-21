"""Run one voice conversation: the pipeline around an agent stack, connect to hang-up.

``BaseConversation`` owns what every flow shares: the call's stats and
transcript, the first agent stack, the ``PipelineWorker`` (metrics, idle timeout,
tracing), the welcome message, cancel-on-disconnect and the call evaluation.
The telephony and browser (WebRTC) flows subclass it for their pipeline shape
and extras (``services/telephony/conversation.py``,
``services/webrtc/conversation.py``).
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List

from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pipecat.frames.frames import (
    BotSpeakingFrame,
    BotStartedSpeakingFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    StopFrame,
    TTSSpeakFrame,
    UserSpeakingFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.transports.base_transport import BaseTransport
from pipecat.utils.tracing.setup import setup_tracing
from pipecat.workers.runner import WorkerRunner

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.log.logger import logger
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.common.agent_stack_builder import (
    StackOptions,
    build_agent_stack,
)
from call_processing.services.common.call_evaluation_service import (
    CallEvaluationService,
)

# 5 minutes without speaking activity ends the conversation
DEFAULT_IDLE_TIMEOUT_SECS = 300

_pipecat_tracing_initialized = False


def _ensure_pipecat_tracing(settings: CallProcessingAppSettings) -> None:
    global _pipecat_tracing_initialized
    if _pipecat_tracing_initialized:
        return
    settings = settings.pipecat
    if settings.enable_tracing and settings.otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otlp_endpoint,
            insecure=True,
        )
        setup_tracing(
            service_name=settings.tracing_service_name,
            exporter=exporter,
            console_export=False,
        )
    _pipecat_tracing_initialized = True


BuildStack = Callable[..., AgentStack]


class BaseConversation(ABC):
    """One voice conversation. Subclasses shape the pipeline for their transport."""

    # Reported as ``telephony.provider`` on the conversation's trace
    provider: str = ''

    def __init__(
        self,
        settings: CallProcessingAppSettings,
        *,
        call_id: str,
        call_direction: str,
        audio_sample_rate: int,
        idle_timeout_secs: int = DEFAULT_IDLE_TIMEOUT_SECS,
    ):
        self.settings = settings
        self.call_id = call_id
        self.call_direction = call_direction
        self.audio_sample_rate = audio_sample_rate
        self.idle_timeout_secs = idle_timeout_secs

    # ------------------------------------------------------------ flow hooks

    @abstractmethod
    def stack_options(self) -> StackOptions:
        """How this flow builds agent stacks (sample rate, prompt suffix, language mode)."""

    @abstractmethod
    def build_pipeline(
        self, transport: BaseTransport, stack: AgentStack, shared: SharedSession
    ) -> List[Any]:
        """The pipeline's processors, from ``transport.input()`` to the end."""

    def span_attributes(self) -> Dict[str, str]:
        """Flow-specific attributes added to the conversation's trace."""
        return {}

    def on_task_created(
        self,
        task: PipelineWorker,
        shared: SharedSession,
        stack: AgentStack,
        build_stack: BuildStack,
    ) -> None:
        """Called once the ``PipelineWorker`` exists, before the pipeline runs."""

    async def close(self) -> None:
        """Release flow-specific resources once the pipeline has stopped."""

    # ------------------------------------------------------------------ run

    async def run(self, transport: BaseTransport, configs: Dict[str, Any]) -> None:
        """Create and run the pipeline until the conversation ends.

        ``configs`` holds ``agent`` (system_prompt, supported_languages,
        default_language, tts_voice_ids, tts/stt parameters, ...),
        ``llm_config``, ``tts_config`` / ``stt_config`` (credentials only) and
        ``tools``.
        """
        _ensure_pipecat_tracing(self.settings)
        pipecat_settings = self.settings.pipecat
        agent_config = configs['agent']
        options = self.stack_options()

        # --- Call evaluation: transcript log and stats (shared by every agent stack) ---
        transcript_log: List[Dict[str, Any]] = []
        call_evaluation_tasks: List[asyncio.Task] = []
        call_stats: Dict[str, Any] = {
            'user_turns': 0,
            'assistant_turns': 0,
            'interruption_count': 0,
            'tool_calls_count': 0,
            'language_switch_count': 0,
            'agent_switch_count': 0,
            '_bot_speaking': False,
        }
        shared = SharedSession(call_stats=call_stats, transcript_log=transcript_log)

        def build_stack(cfg: Dict[str, Any], initial: bool = False) -> AgentStack:
            return build_agent_stack(
                agent_config=cfg['agent'],
                llm_config=cfg['llm_config'],
                tts_config=cfg['tts_config'],
                stt_config=cfg['stt_config'],
                tools=cfg.get('tools') or [],
                shared=shared,
                options=options,
                is_initial_stack=initial,
            )

        stack = build_stack(configs, initial=True)
        shared.active_stack = stack
        agent_id = agent_config.get('id')

        pipeline = Pipeline(self.build_pipeline(transport, stack, shared))

        task = PipelineWorker(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=self.audio_sample_rate,
                audio_out_sample_rate=self.audio_sample_rate,
                enable_metrics=True,
            ),
            idle_timeout_frames=(
                BotSpeakingFrame,
                UserSpeakingFrame,
                BotStartedSpeakingFrame,
                UserStartedSpeakingFrame,
            ),
            idle_timeout_secs=self.idle_timeout_secs,
            enable_tracing=pipecat_settings.enable_tracing,
            enable_turn_tracking=pipecat_settings.enable_turn_tracking,
            conversation_id=None,
            additional_span_attributes={
                'voice_agent.id': str(agent_id) if agent_id else '',
                'voice_agent.name': agent_config.get('name', ''),
                'call.direction': self.call_direction,
                'call.id': self.call_id,
                'telephony.provider': self.provider,
                **self.span_attributes(),
            },
        )

        # Tools (language switch, end_conversation) queue frames on the task
        shared.task_container['task'] = task
        self.on_task_created(task, shared, stack, build_stack)

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
            active = shared.active_stack or stack
            call_stats['language_switch_count'] = call_stats.pop(
                '_prior_language_switches', 0
            ) + active.language_state.get('switch_count', 0)
            if pipecat_settings.enable_tracing and pipecat_settings.otlp_endpoint:
                # Capture the current OTel context now, while the pipecat span is still
                # active. The background task will use this as the parent so call.evaluation
                # appears under the same trace rather than as a new root trace.
                parent_ctx = otel_context.get_current()
                t = asyncio.create_task(
                    CallEvaluationService.record_call_metrics(
                        call_id=self.call_id,
                        agent_config=agent_config,
                        call_outcome=outcome,
                        transcript_log=transcript_log,
                        stats=call_stats,
                        parent_context=parent_ctx,
                        settings=self.settings,
                    )
                )
                call_evaluation_tasks.append(t)

        # WorkerRunner runs the worker in its own task and doesn't re-raise its
        # errors, so they would never reach the except block around run().
        @task.event_handler('on_pipeline_error')
        async def on_pipeline_error(task, frame):
            logger.error(
                f"Pipeline error for agent {agent_config['name']}: {frame.error} "
                f'(processor usable: {getattr(frame.processor, "is_usable", "n/a")})'
            )

        @transport.event_handler('on_client_connected')
        async def on_client_connected(transport, client):
            logger.info(f"Client connected for agent: {agent_config['name']}")
            if stack.welcome_message:
                await task.queue_frame(
                    TTSSpeakFrame(stack.welcome_message, append_to_context=True)
                )

        @transport.event_handler('on_client_disconnected')
        async def on_client_disconnected(transport, client):
            logger.info(f"Client disconnected for agent: {agent_config['name']}")
            await task.cancel()

        runner = WorkerRunner(handle_sigint=False)
        try:
            await runner.add_workers(task)
            await runner.run()
        except Exception as e:
            logger.error(
                f"Pipeline error for agent {agent_config['name']}: {e}",
                exc_info=True,
            )
            raise
        finally:
            await self.close()
            await task.cancel()
            if call_evaluation_tasks:
                await asyncio.gather(*call_evaluation_tasks, return_exceptions=True)
            logger.info(f"Conversation ended for agent: {agent_config['name']}")
