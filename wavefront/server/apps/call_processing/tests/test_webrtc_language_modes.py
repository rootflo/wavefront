"""Per-room language handling: native language rules/tool vs. the app's room context."""

from types import SimpleNamespace
from typing import Any, Dict

import pytest

from call_processing.services import pipecat_service as pipecat_service_module
from call_processing.services.agent_stack import SharedSession
from call_processing.services.pipecat_service import PipecatService

TOOL = 'detect_and_switch_language'
RULES = 'LANGUAGE SWITCHING RULES'
BASE_PROMPT = (
    "IMPORTANT: Don't mention agent name.\n\nYou help the user pick a language."
)


class FakeLLM:
    def __init__(self):
        self.functions: Dict[str, Any] = {}

    def register_function(self, name, func, **kwargs):
        self.functions[name] = func

    def event_handler(self, name):
        return lambda fn: fn


class FakeServiceFactory:
    """Stands in for the LLM/STT/TTS factories: no network, no credentials."""

    @staticmethod
    def create_llm_service(config):
        return FakeLLM()

    @staticmethod
    def create_stt_service(config):
        return SimpleNamespace(name='stt', config=config)

    @staticmethod
    def create_tts_service(config):
        return SimpleNamespace(name='tts', config=config)


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    for name in ('LLMServiceFactory', 'STTServiceFactory', 'TTSServiceFactory'):
        monkeypatch.setattr(pipecat_service_module, name, FakeServiceFactory)


def _build(
    provider='webrtc', languages=('en', 'hi', 'ta'), customer_number='', **kwargs
):
    service = PipecatService(SimpleNamespace(pipecat=SimpleNamespace()))
    return service.build_agent_stack(
        agent_config={
            'id': 'agent-1',
            'name': 'Language agent',
            'system_prompt': BASE_PROMPT,
            'welcome_message': 'Hello',
            'supported_languages': list(languages),
            'default_language': 'en',
            'tts_voice_ids': {'en': 'v-en', 'hi': 'v-hi'},
        },
        llm_config={},
        tts_config={'provider': 'deepgram', 'api_key': 'k'},
        stt_config={'provider': 'deepgram', 'api_key': 'k'},
        tools=[],
        customer_number=customer_number,
        provider=provider,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=16000,
        shared=SharedSession(
            call_stats={
                'user_turns': 0,
                'assistant_turns': 0,
                'interruption_count': 0,
                'tool_calls_count': 0,
                '_bot_speaking': False,
            },
            transcript_log=[],
        ),
        **kwargs,
    )


def _system(stack) -> str:
    return stack.context.get_messages()[0]['content']


def _tool_names(stack):
    return [s.name for s in stack.function_schemas]


def test_native_mode_keeps_language_rules_prefix_and_tool():
    stack = _build()

    assert RULES in _system(stack)
    assert _system(stack).startswith('Respond in English.')
    assert TOOL in _tool_names(stack)
    assert TOOL in stack.llm.functions
    assert RULES in stack.language_state['original_system_prompt']


def test_room_context_mode_leaves_the_prompt_untouched_and_has_no_language_tool():
    stack = _build(room_context_language=True)

    assert RULES not in _system(stack)
    assert 'Respond in' not in _system(stack)
    assert TOOL not in _tool_names(stack)
    assert TOOL not in stack.llm.functions
    assert _system(stack) == BASE_PROMPT
    # Still multi-language so the app's set_context.language can move STT/TTS
    assert stack.supported_languages == ['en', 'hi', 'ta']
    assert stack.language_state['original_system_prompt'] == BASE_PROMPT
    assert RULES not in stack.language_state['original_system_prompt']
    assert stack.language_state['current_language'] == 'en'


def test_webrtc_omits_telephony_phone_and_ist_prefix():
    stack = _build(languages=('en',))

    prompt = _system(stack)
    assert prompt == BASE_PROMPT
    assert 'Customer phone number' not in prompt
    assert 'Current Date and Time (IST)' not in prompt


def test_telephony_includes_phone_and_ist_prefix():
    stack = _build(
        provider='twilio', languages=('en',), customer_number='+911234567890'
    )

    prompt = _system(stack)
    assert prompt.startswith('Customer phone number: +911234567890\n')
    assert 'Current Date and Time (IST)' in prompt
    assert prompt.endswith(BASE_PROMPT)


def test_room_context_mode_keeps_multi_language_stt_and_tts():
    stack = _build(room_context_language=True)

    assert stack.stt.config['parameters']['language'] == 'en'
    assert stack.tts.config['parameters']['language'] == 'en'
    assert stack.tts.config['voice_id'] == 'v-en'


def test_single_language_agent_is_unaffected_by_the_flag():
    native = _build(languages=('en',))
    room_context = _build(languages=('en',), room_context_language=True)

    assert _system(native) == _system(room_context)
    assert RULES not in _system(native)
    assert TOOL not in _tool_names(native) and TOOL not in _tool_names(room_context)
    assert native.supported_languages == room_context.supported_languages == []
