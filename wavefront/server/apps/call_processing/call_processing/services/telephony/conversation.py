"""Phone calls (Twilio / Exotel / Smartflo): one agent, a linear pipeline, 8 kHz audio."""

from typing import Any, Dict, List, Optional

from pipecat.frames.frames import LLMMessagesAppendFrame
from pipecat.transports.base_transport import BaseTransport

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.log.logger import logger
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.common.agent_stack_builder import StackOptions
from call_processing.services.common.audio_config import TELEPHONY_SAMPLE_RATE
from call_processing.services.common.context.caller_block import (
    LATE_WAIT_S,
    PendingFields,
    caller_block,
    late_caller_fields,
    read_caller_fields,
)
from call_processing.services.common.context.compiler import (
    run_in_background,
    start_prefetch,
)
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.conversation import BaseConversation, BuildStack
from call_processing.services.telephony.prompts import call_context


def mask_phone_number(number: str) -> str:
    """Keep the last 4 digits."""
    if number and len(number) > 4:
        return '*' * (len(number) - 4) + number[-4:]
    return number


class TelephonyConversation(BaseConversation):
    def __init__(
        self,
        settings: CallProcessingAppSettings,
        *,
        provider: str,
        call_id: str,
        call_direction: str,
        customer_number: str,
        agent_number: str,
        context_store: Optional[CallContextStore] = None,
    ):
        super().__init__(
            settings,
            call_id=call_id,
            call_direction=call_direction,
            audio_sample_rate=TELEPHONY_SAMPLE_RATE,
        )
        self.provider = provider
        self.customer_number = customer_number
        self.agent_number = agent_number
        if context_store is not None and call_id in ('', None, 'unknown'):
            # Without the provider's call id every such call would share one
            # cache key, so these calls run their tools live, as before
            logger.warning(
                f'No call id from {provider}; caller context and caching are off'
            )
            context_store = None
        self.context_store = context_store
        # Tools get the normalised number; the prompt keeps the raw one
        self.call_subject = CallSubject.for_call(
            call_ref=call_id or '', direction=call_direction, raw_phone=customer_number
        )
        # Filled in run(): the CRM's context, and the <caller_context> block
        self.outbound_context: Dict[str, str] = {}
        self._caller_block = ''
        self._pending_fields: List[PendingFields] = []

    def stack_options(self) -> StackOptions:
        return StackOptions(
            # The block goes last: after the phone number and time, never repeating them
            prompt_suffix=call_context(self.customer_number) + self._caller_block,
            call_subject=self.call_subject,
            context_store=self.context_store,
            outbound_context=self.outbound_context or None,
        )

    async def run(self, transport: BaseTransport, configs: Dict[str, Any]) -> None:
        agent_id = configs['agent'].get('id')
        store = self.context_store
        if store is not None and agent_id:
            try:
                await self._load_caller_context(store, str(agent_id), configs)
            except Exception as e:
                # Never worse than before: the call goes ahead without the block
                logger.error(
                    f'Caller context for call {self.call_subject.call_ref} '
                    f'failed, continuing without it: {e}',
                    exc_info=True,
                )
                self._caller_block = ''
                self._pending_fields = []
        await super().run(transport, configs)

    async def _load_caller_context(
        self, store: CallContextStore, agent_id: str, configs: Dict[str, Any]
    ) -> None:
        tools = configs.get('tools') or []
        if self.call_direction == 'outbound':
            # Saved by /api/calls/prepare while the call rang
            self.outbound_context = await store.read_outbound(
                agent_id, self.call_subject.call_ref
            )
        # Exotel / Smartflo (and Twilio, if its webhook pod didn't): fetch
        # while the stack is built and the greeting plays
        start_prefetch(tools, self.call_subject, agent_id, store, self.outbound_context)
        fields, self._pending_fields = await read_caller_fields(
            tools, self.call_subject, agent_id, store, self.outbound_context
        )
        self._caller_block = caller_block(fields, self.outbound_context)
        logger.info(
            f'Caller context for call {self.call_subject.call_ref}: '
            f'{len(fields)} field(s) ready, {len(self.outbound_context)} from '
            f'the CRM, {len(self._pending_fields)} tool(s) still fetching'
        )

    def on_task_created(
        self,
        task: Any,
        shared: SharedSession,
        stack: AgentStack,
        build_stack: BuildStack,
    ) -> None:
        if self._pending_fields and self.context_store is not None:
            run_in_background(
                self._append_late_fields(task),
                name=f'caller context for call {self.call_subject.call_ref}',
            )

    async def _append_late_fields(self, task: Any) -> None:
        """Fields whose prefetch finished after the prompt was built: added once.

        Appended as a message without an LLM run; the system prompt is never
        rewritten, so its cached prefix stays intact.
        """
        fields = await late_caller_fields(
            self.context_store, self._pending_fields, LATE_WAIT_S
        )
        # The CRM's context is in the prompt already; only the new fields go here
        block = caller_block(fields, None).strip()
        if not block:
            return
        await task.queue_frame(
            LLMMessagesAppendFrame(
                messages=[{'role': 'developer', 'content': block}], run_llm=False
            )
        )
        logger.info(
            f'Caller context for call {self.call_subject.call_ref}: '
            f'{len(fields)} late field(s) appended'
        )

    def build_pipeline(
        self, transport: BaseTransport, stack: AgentStack, shared: SharedSession
    ) -> List[Any]:
        return [
            transport.input(),  # Audio input from the telephony provider
            stack.stt,  # Speech-to-Text
            stack.context_aggregator.user(),  # Add user message to context
            *stack.pre_llm_processors,  # Direct language switch
            stack.llm,  # LLM processing
            stack.filler,  # Thinking / tool-call fillers straight into TTS
            stack.tts,  # Text-to-Speech
            transport.output(),  # Audio output to the telephony provider
            stack.context_aggregator.assistant(),  # Add assistant response to context
        ]

    def span_attributes(self) -> Dict[str, str]:
        return {
            'customer.phone_number': mask_phone_number(self.customer_number),
            'telephony.agent_number': self.agent_number,
        }
