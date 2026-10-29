"""A user turn that only names a language switches before the LLM runs."""

import pytest
from types import SimpleNamespace

from pipecat.frames.frames import (
    LLMContextFrame,
    STTUpdateSettingsFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.tests.utils import run_test

from call_processing.services.common.direct_language_switch import (
    DirectLanguageSwitchProcessor,
    LanguageSwitchConfig,
    match_language_choice,
)
from call_processing.services.common.prompts import language_instruction
from call_processing.services.common.tools.language_detection_tool import (
    LanguageDetectionToolFactory,
)

BASE_PROMPT = 'You help the user.'
SUPPORTED = ['en', 'hi', 'ta']


# ------------------------------------------------------------------- config


def test_direct_switch_is_off_by_default():
    assert LanguageSwitchConfig.from_agent_config({}).direct_switch is False


def test_direct_switch_can_be_turned_on():
    agent = {'conversation_config': {'language_switch': {'direct_switch': True}}}

    assert LanguageSwitchConfig.from_agent_config(agent).direct_switch is True


def test_non_boolean_direct_switch_falls_back_to_the_default():
    agent = {'conversation_config': {'language_switch': {'direct_switch': 'true'}}}

    assert LanguageSwitchConfig.from_agent_config(agent).direct_switch is False


def test_agent_choice_words_are_read_per_language():
    agent = {
        'conversation_config': {
            'language_switch': {
                'choice_words': {'HI': ['Chahiye', 'Hindi mein', 'chahiye', 7]},
            }
        }
    }

    # Lower-cased, split into words, de-duplicated; the language name is dropped
    assert LanguageSwitchConfig.from_agent_config(agent).choice_words == {
        'hi': ('chahiye', 'mein')
    }


def test_malformed_choice_words_are_ignored():
    for value in ('mein', ['mein'], {'hi': 'mein'}):
        agent = {'conversation_config': {'language_switch': {'choice_words': value}}}

        assert LanguageSwitchConfig.from_agent_config(agent).choice_words == {}


# ------------------------------------------------------------------ matching


@pytest.mark.parametrize(
    'text, language',
    [
        ('Hindi.', 'hi'),
        ('hindi', 'hi'),
        ('हिंदी।', 'hi'),
        ('हिन्दी', 'hi'),
        ('Hindi please', 'hi'),
        ('Hindi mein', 'hi'),
        ('हिंदी में', 'hi'),
        ('Hindi. Hindi.', 'hi'),
        ('Yes, English.', 'en'),
        ('Speak Tamil', 'ta'),
        ('Hindi me', 'hi'),
        ('Continue in Hindi please.', 'hi'),
    ],
)
def test_a_bare_language_choice_is_matched(text, language):
    assert match_language_choice(text, SUPPORTED) == language


@pytest.mark.parametrize(
    'text',
    [
        # Filler words alone name no language
        'me',
        'yes',
        'continue',
        'Can we talk in Hindi?',
        'Not Hindi',
        'I need a loan in Hindi',
        'Hindi or English',
        'Kannada',  # not supported by this agent
        'Indy',  # a mishearing is left to the LLM's judgment
        '',
        '...',
        'please',
    ],
)
def test_anything_more_than_a_choice_is_left_to_the_llm(text):
    assert match_language_choice(text, SUPPORTED) is None


def test_choice_words_come_from_the_agents_own_languages():
    # "mein" is a Hindi choice word: it helps only an agent that speaks Hindi
    assert match_language_choice('Tamil mein', ['en', 'ta']) is None
    assert match_language_choice('Tamil mein', ['en', 'hi', 'ta']) == 'ta'
    # and a Tamil one helps only a Tamil agent
    assert match_language_choice('Tamil la', ['en', 'ta']) == 'ta'
    assert match_language_choice('Hindi la', ['en', 'hi']) is None


def test_an_agent_list_replaces_that_languages_built_ins():
    words = {'hi': ['chahiye']}

    assert match_language_choice('Hindi chahiye', ['en', 'hi']) is None
    assert match_language_choice('Hindi chahiye', ['en', 'hi'], words) == 'hi'
    # "mein" was a built-in Hindi word; this agent's list no longer has it
    assert match_language_choice('Hindi mein', ['en', 'hi'], words) is None
    # English and the other languages keep their built-ins
    assert match_language_choice('Hindi please', ['en', 'hi'], words) == 'hi'


def test_an_agent_can_drop_a_languages_choice_words():
    assert match_language_choice('Hindi please', ['en', 'hi'], {'en': []}) is None


def test_choice_words_of_a_language_the_agent_lacks_are_ignored():
    words = {'ta': ['chahiye']}

    assert match_language_choice('Hindi chahiye', ['en', 'hi'], words) is None


def test_english_choice_words_help_every_agent():
    assert match_language_choice('Tamil please', ['ta', 'te']) == 'ta'


def test_multi_word_language_names_match():
    assert match_language_choice('Bahasa Indonesia', ['en', 'id']) == 'id'


def test_a_name_shared_by_two_supported_languages_is_left_to_the_llm():
    assert match_language_choice('Filipino', ['en', 'fil', 'tl']) is None
    assert match_language_choice('Filipino', ['en', 'fil']) == 'fil'


# ----------------------------------------------------------------- processor


class FakeTask:
    def __init__(self):
        self.queued = []

    async def queue_frame(self, frame):
        self.queued.append(frame)


class Harness:
    def __init__(self, user_text: str, enabled: bool = True, current: str = 'en'):
        self.context = LLMContext(
            [
                {
                    'role': 'system',
                    'content': f'{language_instruction(current)}\n\n{BASE_PROMPT}',
                },
                {'role': 'assistant', 'content': 'Which language would you like?'},
                {'role': 'user', 'content': user_text},
            ]
        )
        self.task = FakeTask()
        self.selected = []
        self.state = {
            'current_language': current,
            'switch_count': 0,
            'original_system_prompt': BASE_PROMPT,
        }

        async def on_selected(language):
            self.selected.append(language)

        self.processor = DirectLanguageSwitchProcessor(
            enabled=enabled,
            supported_languages=SUPPORTED,
            language_state=self.state,
            task_container={'task': self.task},
            tts_provider='sarvam',
            stt_provider='sarvam',
            tts_voice_ids={'hi': 'v-hi'},
            on_language_selected=on_selected,
        )

    async def run(self):
        down, _ = await run_test(
            self.processor, frames_to_send=[LLMContextFrame(self.context)]
        )
        return [type(f) for f in down]

    def messages(self):
        return self.context.get_messages()


async def test_a_bare_language_name_switches_before_the_llm_runs():
    h = Harness('Hindi.')

    down = await h.run()

    # The voice change reaches the TTS ahead of the context the LLM answers
    assert down == [TTSUpdateSettingsFrame, LLMContextFrame]
    assert [type(f) for f in h.task.queued] == [STTUpdateSettingsFrame]
    assert h.messages()[0]['content'] == (
        f"{language_instruction('hi')}\n\n{BASE_PROMPT}"
    )
    assert h.state['current_language'] == 'hi'
    assert h.state['switch_count'] == 1
    assert h.selected == ['hi']
    # The LLM is told the switch is done, so it answers instead of calling the tool
    note = h.messages()[-1]
    assert note['role'] == 'developer'
    assert 'Hindi' in note['content']


async def test_choosing_the_current_language_adds_the_note_without_switching():
    h = Harness('English', current='en')

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.task.queued == []
    assert h.state['switch_count'] == 0
    assert h.selected == ['en']
    assert h.messages()[-1]['role'] == 'developer'


async def test_off_passes_the_turn_to_the_llm_untouched():
    h = Harness('Hindi.', enabled=False)

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.task.queued == []
    assert h.state['current_language'] == 'en'
    assert h.messages()[-1] == {'role': 'user', 'content': 'Hindi.'}


async def test_a_sentence_about_a_language_goes_to_the_llm_tool():
    h = Harness('Can we talk in Hindi?')

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.task.queued == []
    assert h.state['current_language'] == 'en'
    assert h.selected == []


async def test_a_run_that_does_not_end_on_a_user_message_is_left_alone():
    h = Harness('Hindi.')
    h.context.add_message({'role': 'developer', 'content': 'Check in on the user.'})

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.state['current_language'] == 'en'


async def test_without_a_pipeline_task_nothing_is_switched():
    h = Harness('Hindi.')
    h.processor._task_container = {'task': None}

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.state['current_language'] == 'en'
    assert h.messages()[-1]['role'] == 'user'


async def test_providers_that_cannot_switch_at_runtime_still_switch_the_prompt():
    h = Harness('Hindi.')
    h.processor._tts_provider = 'unknown'
    h.processor._stt_provider = 'unknown'

    down = await h.run()

    # No settings frames to send, but the LLM still answers in Hindi
    assert down == [LLMContextFrame]
    assert h.task.queued == []
    assert h.state['current_language'] == 'hi'
    assert h.messages()[0]['content'].startswith(language_instruction('hi'))


async def test_a_language_without_its_own_voice_keeps_the_voice_and_changes_language():
    h = Harness('Hindi.')
    h.processor._tts_voice_ids = {}

    down = await h.run()

    assert down == [TTSUpdateSettingsFrame, LLMContextFrame]
    assert h.state['current_language'] == 'hi'


async def test_without_a_base_prompt_nothing_is_switched():
    h = Harness('Hindi.')
    h.state['original_system_prompt'] = ''

    down = await h.run()

    assert down == [LLMContextFrame]
    assert h.task.queued == []
    assert h.state['current_language'] == 'en'
    assert h.messages()[-1]['role'] == 'user'


async def test_a_failing_app_notification_does_not_break_the_turn():
    h = Harness('Hindi.')

    async def broken(language):
        raise RuntimeError('app went away')

    h.processor._on_language_selected = broken

    down = await h.run()

    assert down == [TTSUpdateSettingsFrame, LLMContextFrame]
    assert h.state['current_language'] == 'hi'


async def test_an_upstream_context_frame_is_left_alone():
    h = Harness('Hindi.')

    _, up = await run_test(
        h.processor,
        frames_to_send=[LLMContextFrame(h.context)],
        frames_to_send_direction=FrameDirection.UPSTREAM,
    )

    assert [type(f) for f in up] == [LLMContextFrame]
    assert h.state['current_language'] == 'en'


# ------------------------------------------- detect_and_switch_language (tool)


class ToolHarness:
    def __init__(self, base_prompt: str = BASE_PROMPT):
        self.context = LLMContext(
            [
                {
                    'role': 'system',
                    'content': f"{language_instruction('en')}\n\n{BASE_PROMPT}",
                },
                {'role': 'user', 'content': 'Can we talk in Hindi?'},
            ]
        )
        self.task = FakeTask()
        self.selected = []
        self.state = {
            'current_language': 'en',
            'switch_count': 0,
            'original_system_prompt': base_prompt,
        }

        async def on_selected(language):
            self.selected.append(language)

        self.tool = LanguageDetectionToolFactory.create_language_detection_tool(
            task_container={'task': self.task},
            tts_provider='sarvam',
            stt_provider='sarvam',
            tts_voice_ids={'hi': 'v-hi'},
            context_container={'context': self.context},
            supported_languages=SUPPORTED,
            default_language='en',
            language_state=self.state,
            on_language_selected=on_selected,
        )

    async def call(self, target: str):
        results = []

        async def result_callback(result, **kwargs):
            results.append(result)

        await self.tool(
            SimpleNamespace(
                arguments={'target_language': target, 'user_intent': target},
                result_callback=result_callback,
            )
        )
        return results[-1]


async def test_the_tool_switches_services_prompt_and_state():
    h = ToolHarness()

    result = await h.call('hi')

    assert result['success'] is True and result['switch_performed'] is True
    assert [type(f) for f in h.task.queued] == [
        TTSUpdateSettingsFrame,
        STTUpdateSettingsFrame,
    ]
    assert h.context.get_messages()[0]['content'] == (
        f"{language_instruction('hi')}\n\n{BASE_PROMPT}"
    )
    assert h.state['current_language'] == 'hi'
    assert h.state['switch_count'] == 1
    assert h.selected == ['hi']


async def test_the_tool_does_nothing_for_the_current_language():
    h = ToolHarness()

    result = await h.call('en')

    assert result['switch_performed'] is False
    assert h.task.queued == []
    assert h.selected == ['en']


async def test_the_tool_refuses_an_unsupported_language():
    h = ToolHarness()

    result = await h.call('kn')

    assert result['success'] is False
    assert h.task.queued == []
    assert h.state['current_language'] == 'en'


async def test_the_tool_reports_a_missing_base_prompt():
    h = ToolHarness(base_prompt='')

    result = await h.call('hi')

    assert result == {
        'success': False,
        'error': 'Original system prompt not found in language state',
    }
    assert h.state['current_language'] == 'en'


async def test_the_processor_uses_the_agents_choice_words():
    h = Harness('Hindi chahiye')
    h.processor._choice_words = {'hi': ('chahiye',)}

    down = await h.run()

    assert down == [TTSUpdateSettingsFrame, LLMContextFrame]
    assert h.state['current_language'] == 'hi'
