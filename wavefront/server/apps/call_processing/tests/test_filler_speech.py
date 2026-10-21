from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    LLMFullResponseStartFrame,
    TTSSpeakFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.tests.utils import SleepFrame, run_test
from pipecat.turns.types import ProcessFrameResult

from call_processing.constants.filler_phrases import FILLER_PHRASES, THINKING_PHRASES
from call_processing.services.common.filler_speech import (
    THINKING_FILLER_DELAY_SECS,
    FillerSpeechConfig,
    FillerSpeechProcessor,
)
from call_processing.services.common.turn_taking import VADWhenBotSilentStartStrategy

# ------------------------------------------------------------------- config


def test_agent_without_filler_config_gets_defaults():
    config = FillerSpeechConfig.from_agent_config({})

    assert config.thinking is False
    assert config.before_tool_call is False
    assert config.thinking_delay_secs == THINKING_FILLER_DELAY_SECS
    assert config.thinking_phrases_for('hi') == THINKING_PHRASES['hi']
    assert config.tool_call_phrases_for('ta') == FILLER_PHRASES['ta']


def test_agent_conversation_config_overrides_defaults():
    agent = {
        'conversation_config': {
            'filler_speech': {
                'thinking': True,
                'thinking_delay_ms': 1200,
                'before_tool_call': True,
                'tool_call_phrases': {'en': ['One sec', '  ', 7]},
            }
        }
    }
    config = FillerSpeechConfig.from_agent_config(agent)

    assert config.thinking is True
    assert config.thinking_delay_secs == 1.2
    assert config.before_tool_call is True
    assert config.tool_call_phrases_for('en') == ['One sec']


def test_conversation_config_stored_as_a_json_string_is_read():
    agent = {'conversation_config': '{"filler_speech": {"thinking": true}}'}

    assert FillerSpeechConfig.from_agent_config(agent).thinking is True


def test_custom_phrases_never_put_english_into_another_language():
    agent = {
        'conversation_config': {
            'filler_speech': {'thinking_phrases': {'en': ['Umm']}},
        }
    }
    config = FillerSpeechConfig.from_agent_config(agent)

    assert config.thinking_phrases_for('en') == ['Umm']
    assert config.thinking_phrases_for('hi') == THINKING_PHRASES['hi']


def test_invalid_delay_is_ignored_and_large_delays_are_capped():
    bad = {'conversation_config': {'filler_speech': {'thinking_delay_ms': 'soon'}}}
    huge = {'conversation_config': {'filler_speech': {'thinking_delay_ms': 60000}}}

    assert (
        FillerSpeechConfig.from_agent_config(bad).thinking_delay_secs
        == THINKING_FILLER_DELAY_SECS
    )
    assert FillerSpeechConfig.from_agent_config(huge).thinking_delay_secs == 5.0


# ---------------------------------------------------------------- processor


class ArmOnUserStop(FillerSpeechProcessor):
    """Arms the thinking filler the way the user aggregator handler does."""

    async def process_frame(self, frame, direction):
        if isinstance(frame, UserStoppedSpeakingFrame):
            await self.arm_thinking_filler(['Hmm'])
        await super().process_frame(frame, direction)


def _spoken(frames):
    return [f.text for f in frames if isinstance(f, TTSSpeakFrame)]


async def test_slow_llm_gets_a_thinking_filler():
    down, _ = await run_test(
        ArmOnUserStop(delay_secs=0.05),
        frames_to_send=[UserStoppedSpeakingFrame(), SleepFrame(sleep=0.2)],
    )

    assert _spoken(down) == ['Hmm']


async def test_fast_llm_gets_no_filler():
    down, _ = await run_test(
        ArmOnUserStop(delay_secs=0.2),
        frames_to_send=[
            UserStoppedSpeakingFrame(),
            LLMFullResponseStartFrame(),
            SleepFrame(sleep=0.3),
        ],
    )

    assert _spoken(down) == []


async def test_filler_is_not_repeated_back_to_back():
    processor = FillerSpeechProcessor()
    picks = [processor._pick(['Hmm', 'Okay']) for _ in range(20)]

    assert all(a != b for a, b in zip(picks, picks[1:]))


# ----------------------------------------------------------- barge-in rules


async def test_vad_starts_the_turn_only_while_the_bot_is_silent():
    strategy = VADWhenBotSilentStartStrategy()
    started = []

    async def on_started(*_):
        started.append(True)

    strategy.add_event_handler('on_user_turn_started', on_started)

    await strategy.process_frame(BotStartedSpeakingFrame())
    result = await strategy.process_frame(VADUserStartedSpeakingFrame())
    assert result == ProcessFrameResult.CONTINUE  # MinWords decides barge-in
    assert started == []

    await strategy.process_frame(BotStoppedSpeakingFrame())
    result = await strategy.process_frame(VADUserStartedSpeakingFrame())
    assert result == ProcessFrameResult.STOP
    assert started == [True]
