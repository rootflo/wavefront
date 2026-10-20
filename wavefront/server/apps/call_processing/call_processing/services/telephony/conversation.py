"""Phone calls (Twilio / Exotel / Smartflo): one agent, a linear pipeline, 8 kHz audio."""

from typing import Any, Dict, List

from pipecat.transports.base_transport import BaseTransport

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.common.agent_stack_builder import StackOptions
from call_processing.services.common.audio_config import TELEPHONY_SAMPLE_RATE
from call_processing.services.common.conversation import BaseConversation
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

    def stack_options(self) -> StackOptions:
        return StackOptions(prompt_suffix=call_context(self.customer_number))

    def build_pipeline(
        self, transport: BaseTransport, stack: AgentStack, shared: SharedSession
    ) -> List[Any]:
        return [
            transport.input(),  # Audio input from the telephony provider
            stack.stt,  # Speech-to-Text
            stack.context_aggregator.user(),  # Add user message to context
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
