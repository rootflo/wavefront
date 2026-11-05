"""Browser (WebRTC) rooms: wideband audio, app messages and agent hot-swap.

On top of the common conversation, a room gets:
    - a ``ClientSessionMessenger``: app messages (set_context / interrupt /
      switch_agent) in, agent_state / caption / transcript events out (RTVI)
    - the agent's processors in ``SwappableSlot``s so the voice agent can change
      without touching the transport (and so the peer connection)
    - STT/TTS forced onto the room's sample rate (never the 8 kHz telephony defaults)
"""

from typing import Any, List, Optional

from pipecat.pipeline.worker import PipelineWorker
from pipecat.transports.base_transport import BaseTransport

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.common.agent_stack_builder import StackOptions
from call_processing.services.common.conversation import BaseConversation, BuildStack
from call_processing.services.webrtc.agent_swap import (
    AgentSwapController,
    SessionHooks,
    SwappableSlot,
)
from call_processing.services.webrtc.app_messages import (
    BotCaptionProcessor,
    ClientSessionMessenger,
)

WEBRTC_PROVIDER = 'webrtc'


class WebRTCConversation(BaseConversation):
    provider = WEBRTC_PROVIDER

    def __init__(
        self,
        settings: CallProcessingAppSettings,
        *,
        room_id: str,
        sample_rate: int,
        idle_timeout_secs: int,
        session_hooks: Optional[SessionHooks] = None,
        room_context_handles_language: bool = False,
    ):
        """
        Args:
            session_hooks: Enables hot-swapping the voice agent in the live room
                and receives the swap controller via ``on_ready`` once the
                pipeline task exists.
            room_context_handles_language: The app drives the language via
                ``set_context.language``, so agents (including ones swapped in
                later) get no language rules / language tool.
        """
        super().__init__(
            settings,
            call_id=room_id,
            call_direction='inbound',
            audio_sample_rate=sample_rate,
            idle_timeout_secs=idle_timeout_secs,
        )
        self.session_hooks = session_hooks
        self.room_context_language = room_context_handles_language
        self.messenger: Optional[ClientSessionMessenger] = None
        self.swap_controller: Optional[AgentSwapController] = None
        self._slot_stt: Optional[SwappableSlot] = None
        self._slot_a: Optional[SwappableSlot] = None
        self._slot_tts: Optional[SwappableSlot] = None
        self._slot_b: Optional[SwappableSlot] = None

    def stack_options(self) -> StackOptions:
        return StackOptions(
            service_sample_rate=self.audio_sample_rate,
            room_context_language=self.room_context_language,
        )

    def build_pipeline(
        self, transport: BaseTransport, stack: AgentStack, shared: SharedSession
    ) -> List[Any]:
        self.messenger = ClientSessionMessenger(
            context=stack.context,
            function_schemas=stack.function_schemas,
            language_state=stack.language_state,
            always_allowed_tools=(
                [] if self.room_context_language else ['detect_and_switch_language']
            ),
            room_context_language=self.room_context_language,
            supported_languages=stack.supported_languages,
            tts_provider=stack.tts_provider,
            stt_provider=stack.stt_provider,
            tts_voice_ids=stack.tts_voice_ids,
        )
        shared.messenger = self.messenger

        # STT and TTS get slots of their own so a swap can keep them connected
        self._slot_stt = SwappableSlot([stack.stt], name='AgentSlotSTT')
        self._slot_a = SwappableSlot(stack.slot_a_processors, name='AgentSlotA')
        self._slot_tts = SwappableSlot([stack.tts], name='AgentSlotTTS')
        self._slot_b = SwappableSlot(stack.slot_b_processors, name='AgentSlotB')
        return [
            transport.input(),  # Audio input from the browser
            self._slot_stt,  # Speech-to-Text
            self._slot_a,  # User aggregator -> LLM -> fillers
            self._slot_tts,  # Text-to-Speech
            transport.output(),  # Audio output to the browser
            # After output so captions follow what the bot is actually saying
            BotCaptionProcessor(self.messenger),
            self._slot_b,  # Add assistant response to context
        ]

    def on_task_created(
        self,
        task: PipelineWorker,
        shared: SharedSession,
        stack: AgentStack,
        build_stack: BuildStack,
    ) -> None:
        messenger = self.messenger
        messenger.bind_task(task)

        hooks = self.session_hooks
        if hooks and hooks.swap:
            self.swap_controller = AgentSwapController(
                slot_stt=self._slot_stt,
                slot_a=self._slot_a,
                slot_tts=self._slot_tts,
                slot_b=self._slot_b,
                task=task,
                messenger=messenger,
                shared=shared,
                build_stack=build_stack,
                stack=stack,
                options=hooks.swap,
            )
            messenger.set_switch_handler(self.swap_controller.request_switch)

        @task.rtvi.event_handler('on_client_message')
        async def on_client_message(rtvi, message):
            await messenger.handle_client_message(message)

        if hooks and hooks.on_ready:
            hooks.on_ready(self.swap_controller)

    async def close(self) -> None:
        if self.swap_controller:
            await self.swap_controller.close()
        if self.messenger:
            await self.messenger.close()
