"""System prompts and tool schemas must not drift when prompt text is reorganised.

``golden/agent_stack_prompts.json`` holds what each flow produced before the
prompt text moved into ``prompts.py`` modules. Regenerate it only for an
intentional wording change.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from call_processing.services.common.agent_stack import SharedSession
from call_processing.services.common.agent_stack_builder import (
    StackOptions,
    build_agent_stack,
)
from call_processing.services.telephony.prompts import call_context
from tests.test_webrtc_language_modes import BASE_PROMPT, fake_services  # noqa: F401

GOLDEN = json.loads(
    (Path(__file__).parent / 'golden' / 'agent_stack_prompts.json').read_text()
)
NOW = datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc)
TELEPHONY = StackOptions(prompt_suffix=call_context('+911234567890', now=NOW))
CASES = {
    'telephony_single': (['en'], TELEPHONY),
    'telephony_multi': (['en', 'hi', 'ta'], TELEPHONY),
    'webrtc_native': (['en', 'hi', 'ta'], StackOptions(service_sample_rate=16000)),
    'webrtc_room_context': (
        ['en', 'hi', 'ta'],
        StackOptions(service_sample_rate=16000, room_context_language=True),
    ),
}


@pytest.mark.parametrize('case', sorted(CASES))
def test_prompts_and_tool_schemas_match_golden(case):
    languages, options = CASES[case]
    stack = build_agent_stack(
        agent_config={
            'id': 'agent-1',
            'name': 'A',
            'system_prompt': BASE_PROMPT,
            'welcome_message': 'Hi',
            'supported_languages': languages,
            'default_language': 'en',
            'tts_voice_ids': {'en': 'v-en', 'hi': 'v-hi'},
            'conversation_config': {'end_conversation': {'enabled': True}},
        },
        llm_config={},
        tts_config={'provider': 'deepgram', 'api_key': 'k'},
        stt_config={'provider': 'deepgram', 'api_key': 'k'},
        tools=[],
        shared=SharedSession(call_stats={}, transcript_log=[]),
        options=options,
    )

    expected = GOLDEN[case]
    assert stack.context.get_messages()[0]['content'] == expected['system']
    assert (
        stack.language_state['original_system_prompt']
        == (expected['original_system_prompt'])
    )
    assert [f.to_default_dict() for f in stack.function_schemas] == expected['tools']
