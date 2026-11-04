from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    EndFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMTextFrame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)

from call_processing.services.common.turn_latency import (
    TurnLatency,
    TurnLatencyObserver,
    TurnLatencyTracker,
    latency_summary,
)

# ------------------------------------------------------------------ tracker


def test_plain_turn_is_timed_to_first_llm_audio():
    t = TurnLatencyTracker()
    t.user_stopped(10.0)
    t.llm_text()
    t.audio(10.6)
    t.audio(10.7)

    turn = t.close()

    assert turn == TurnLatency(answer_secs=pytest.approx(0.6), tool_secs={})
    assert not turn.used_tool


def test_filler_audio_does_not_count_as_the_answer():
    t = TurnLatencyTracker()
    t.user_stopped(10.0)
    t.audio(10.8)  # thinking filler: no LLM text before it
    t.llm_text()
    t.audio(11.2)

    assert t.close().answer_secs == pytest.approx(1.2)


def test_tool_turn_is_timed_to_audio_after_the_last_tool_result():
    t = TurnLatencyTracker()
    t.user_stopped(10.0)
    t.llm_text()  # "Let me check" from the LLM before the call
    t.audio(10.4)
    t.tool_started('c1', 'get_customer_accounts', 10.5)
    t.audio(10.6)  # "One sec" filler
    t.tool_finished('c1', 11.1)
    t.llm_text()
    t.audio(11.7)

    turn = t.close()

    assert turn.answer_secs == pytest.approx(1.7)
    assert turn.tool_secs == {'get_customer_accounts': pytest.approx(0.6)}
    assert turn.used_tool


def test_repeated_tool_time_is_summed():
    t = TurnLatencyTracker()
    t.user_stopped(0.0)
    t.tool_started('a', 'lookup', 0.1)
    t.tool_finished('a', 0.3)
    t.tool_started('b', 'lookup', 0.4)
    t.tool_finished('b', 0.9)
    t.llm_text()
    t.audio(1.2)

    assert t.close().tool_secs == {'lookup': pytest.approx(0.7)}


def test_unanswered_turn_is_dropped():
    t = TurnLatencyTracker()
    t.user_stopped(0.0)
    t.audio(0.5)  # filler only, then the caller talks again

    assert t.close() is None
    assert not t.turn_open


def test_tool_started_outside_a_turn_is_ignored():
    t = TurnLatencyTracker()
    t.tool_started('x', 'lookup', 0.0)
    t.tool_finished('x', 1.0)

    assert t.close() is None


def test_new_user_turn_closes_the_previous_one():
    t = TurnLatencyTracker()
    t.user_stopped(0.0)
    t.llm_text()
    t.audio(0.5)

    closed = t.user_stopped(5.0)

    assert closed.answer_secs == pytest.approx(0.5)
    assert t.turn_open


# ----------------------------------------------------------------- observer


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def _push(observer, clock, at, frame):
    clock.now = at
    await observer.on_push_frame(SimpleNamespace(frame=frame))


def _audio():
    return TTSAudioRawFrame(audio=b'\x00\x00', sample_rate=8000, num_channels=1)


async def test_observer_reports_tool_turn_from_frames():
    clock = _Clock()
    turns = []
    obs = TurnLatencyObserver(on_turn=turns.append, clock=clock)

    await _push(obs, clock, 1.0, UserStoppedSpeakingFrame())
    await _push(
        obs,
        clock,
        1.3,
        FunctionCallInProgressFrame(
            function_name='get_customer_accounts', tool_call_id='c1', arguments={}
        ),
    )
    await _push(obs, clock, 1.4, _audio())  # filler
    await _push(
        obs,
        clock,
        2.0,
        FunctionCallResultFrame(
            function_name='get_customer_accounts',
            tool_call_id='c1',
            arguments={},
            result={},
        ),
    )
    await _push(obs, clock, 2.3, LLMTextFrame(text='Your due date'))
    await _push(obs, clock, 2.5, _audio())
    await _push(obs, clock, 6.0, UserStartedSpeakingFrame())

    assert len(turns) == 1
    assert turns[0].answer_secs == pytest.approx(1.5)
    assert turns[0].tool_secs == {'get_customer_accounts': pytest.approx(0.7)}


async def test_observer_closes_last_turn_at_end_of_call():
    clock = _Clock()
    turns = []
    obs = TurnLatencyObserver(on_turn=turns.append, clock=clock)

    await _push(obs, clock, 0.0, UserStoppedSpeakingFrame())
    await _push(obs, clock, 0.2, LLMTextFrame(text='Bye'))
    await _push(obs, clock, 0.4, _audio())
    await _push(obs, clock, 1.0, EndFrame())

    assert [t.answer_secs for t in turns] == [pytest.approx(0.4)]


# ------------------------------------------------------------------ summary


def test_summary_splits_tool_turns():
    turns = [
        TurnLatency(answer_secs=0.6),
        TurnLatency(answer_secs=0.8),
        TurnLatency(answer_secs=1.9, tool_secs={'lookup': 0.7}),
    ]

    summary = latency_summary(turns)

    assert summary['call.turn_latency_count'] == 3
    assert summary['call.turn_latency_p50_secs'] == 0.8
    assert summary['call.turn_latency_max_secs'] == 1.9
    assert summary['call.tool_turn_latency_count'] == 1
    assert summary['call.tool_turn_latency_p50_secs'] == 1.9
    assert summary['call.tool_exec_p50_secs'] == 0.7


def test_summary_of_no_turns_is_empty():
    assert latency_summary([]) == {}
