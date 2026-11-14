"""Language packs and the cache-friendly prompt layout. Made-up prompts only."""

import logging

from pipecat.processors.aggregators.llm_context import LLMContext

from call_processing.services.common.agent_stack import SharedSession
from call_processing.services.common.agent_stack_builder import (
    StackOptions,
    build_agent_stack,
)
from call_processing.services.common.language_switch import set_prompt_language
from call_processing.services.common.prompt_layout import (
    PromptParts,
    build_system_prompt,
    language_packs,
)

# Its autouse fixture swaps the LLM/STT/TTS factories for fakes
from tests.test_webrtc_language_modes import fake_services  # noqa: F401

MAIN = 'You are the water helpline assistant.'
PARTS = PromptParts(
    main=MAIN,
    rules='\n\nLANGUAGE SWITCHING RULES',
    suffix='\n\nCustomer phone number: +911234567890',
    packs={'ta': 'TAMIL PACK', 'hi': 'HINDI PACK'},
)


def test_layout_order_is_main_pack_rules_call_details_then_language():
    prompt = build_system_prompt(PARTS, 'ta')

    assert prompt == (
        f'{MAIN}\n\nTAMIL PACK\n\nLANGUAGE SWITCHING RULES'
        '\n\nCustomer phone number: +911234567890'
        '\n\nRespond in Tamil (தமிழில் பதிலளிக்கவும்).'
        ' Current language: Tamil.'
    )


def test_a_language_without_a_pack_adds_nothing_but_the_last_line():
    prompt = build_system_prompt(PARTS, 'en')

    assert 'PACK' not in prompt
    assert prompt.endswith('Respond in English. Current language: English.')


def test_switching_keeps_the_main_prompt_as_an_unchanged_prefix():
    tamil = build_system_prompt(PARTS, 'ta')
    hindi = build_system_prompt(PARTS, 'hi')

    assert tamil.startswith(MAIN) and hindi.startswith(MAIN)
    # Only ever one pack
    assert 'TAMIL PACK' not in hindi and 'HINDI PACK' in hindi


def test_packs_only_for_supported_languages_and_only_text(caplog):
    agent = {
        'conversation_config': {
            'language_prompts': {
                'ta': '  Tamil rules  ',
                'fr': 'French rules',  # not supported by this agent
                'hi': ['not', 'text'],
                'ml': '   ',
            }
        }
    }
    with caplog.at_level(logging.WARNING, logger='call_processing'):
        packs = language_packs(agent, ['en', 'ta', 'hi', 'ml'])

    assert packs == {'ta': 'Tamil rules'}
    assert "'fr' ignored" in caplog.text and "'hi' ignored" in caplog.text


def test_packs_read_from_stored_json_text():
    agent = {'conversation_config': '{"language_prompts": {"ta": "Tamil rules"}}'}
    assert language_packs(agent, ['en', 'ta']) == {'ta': 'Tamil rules'}


def test_switch_rebuilds_from_parts_and_keeps_the_conversation():
    context = LLMContext(
        [
            {'role': 'system', 'content': build_system_prompt(PARTS, 'en')},
            {'role': 'assistant', 'content': 'Which language would you like?'},
            {'role': 'user', 'content': 'Tamil'},
        ]
    )
    state = {'prompt_parts': PARTS, 'original_system_prompt': 'OLD BASE'}

    assert set_prompt_language(context, state, 'ta') is True

    messages = context.get_messages()
    assert messages[0]['content'] == build_system_prompt(PARTS, 'ta')
    assert [m['content'] for m in messages[1:]] == [
        'Which language would you like?',
        'Tamil',
    ]


def _stack(config, default_language='en'):
    return build_agent_stack(
        agent_config={
            'id': 'agent-1',
            'name': 'A',
            'system_prompt': MAIN,
            'welcome_message': 'Hi',
            'supported_languages': ['en', 'ta'],
            'default_language': default_language,
            'tts_voice_ids': {'en': 'v-en', 'ta': 'v-ta'},
            'conversation_config': config,
        },
        llm_config={},
        tts_config={'provider': 'deepgram', 'api_key': 'k'},
        stt_config={'provider': 'deepgram', 'api_key': 'k'},
        tools=[],
        shared=SharedSession(call_stats={}, transcript_log=[]),
        options=StackOptions(prompt_suffix='\n\nCustomer phone number: +911234567890'),
    )


def test_call_starts_with_the_default_languages_pack_only():
    config = {'language_prompts': {'ta': 'TAMIL PACK'}}

    english = _stack(config).context.get_messages()[0]['content']
    tamil = _stack(config, 'ta').context.get_messages()[0]['content']

    assert 'TAMIL PACK' not in english
    assert english.startswith(MAIN)
    assert tamil.startswith(f'{MAIN}\n\nTAMIL PACK')
    assert tamil.endswith('Current language: Tamil.')


def test_a_live_switch_swaps_in_the_pack():
    stack = _stack({'language_prompts': {'ta': 'TAMIL PACK'}})

    set_prompt_language(stack.context, stack.language_state, 'ta')

    prompt = stack.context.get_messages()[0]['content']
    assert prompt.startswith(f'{MAIN}\n\nTAMIL PACK')
    assert prompt.count('Current language:') == 1
    assert prompt.endswith('Current language: Tamil.')
