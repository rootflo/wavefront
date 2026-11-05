import time

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_start import (
    MinWordsUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)

from call_processing.services.common.smart_turn import SharedSmartTurnAnalyzer
from call_processing.services.common.turn_taking import (
    LATE_TRANSCRIPT_SECS,
    TALK_OVER_TRANSCRIPT_SECS,
    TranscriptFallbackStartStrategy,
    TurnTakingConfig,
    VADWhenBotSilentStartStrategy,
)


def _agent(turn_taking):
    return {'conversation_config': {'turn_taking': turn_taking}}


def test_agent_without_turn_taking_config_gets_defaults():
    config = TurnTakingConfig.from_agent_config({})

    assert config == TurnTakingConfig()
    assert config.barge_in is True
    assert config.barge_in_min_words == 0
    vad = config.vad_params()
    assert (vad.confidence, vad.min_volume, vad.start_secs, vad.stop_secs) == (
        0.75,
        0.65,
        0.2,
        0.2,
    )


def test_agent_overrides_are_applied_in_ms_and_seconds():
    config = TurnTakingConfig.from_agent_config(
        _agent(
            {
                'barge_in': True,
                'barge_in_min_words': 3,
                'vad_confidence': 0.8,
                'vad_min_volume': 0.5,
                'vad_start_ms': 150,
                'vad_stop_ms': 300,
                'end_of_turn_timeout_ms': 2000,
            }
        )
    )

    assert config.barge_in is True
    assert config.barge_in_min_words == 3
    assert config.vad_confidence == 0.8
    assert config.vad_min_volume == 0.5
    assert config.vad_start_secs == 0.15
    assert config.vad_stop_secs == 0.3
    assert config.end_of_turn_timeout_secs == 2.0


def test_out_of_range_values_are_clamped_and_junk_is_ignored():
    config = TurnTakingConfig.from_agent_config(
        _agent(
            {
                'barge_in': 'true',
                'barge_in_min_words': 99,
                'vad_confidence': 5,
                'vad_stop_ms': 'fast',
                'end_of_turn_timeout_ms': True,
            }
        )
    )

    assert config.barge_in is True  # a non-boolean falls back to the default
    assert config.barge_in_min_words == 10
    assert config.vad_confidence == 0.95
    assert config.vad_stop_secs == 0.2
    assert config.end_of_turn_timeout_secs == 3.0


def test_strategies_carry_the_agent_settings():
    config = TurnTakingConfig.from_agent_config(
        _agent(
            {
                'barge_in': True,
                'barge_in_min_words': 4,
                'end_of_turn_timeout_ms': 1500,
            }
        )
    )

    vad_start, min_words = config.start_strategies()
    assert isinstance(vad_start, VADWhenBotSilentStartStrategy)
    assert isinstance(min_words, MinWordsUserTurnStartStrategy)
    assert min_words._min_words == 4

    (stop,) = config.stop_strategies()
    analyzer = stop._turn_analyzer
    assert isinstance(analyzer, SharedSmartTurnAnalyzer)
    assert analyzer.params.stop_secs == 1.5


# ------------------------------------------------------------ barge-in modes


def test_default_is_instant_barge_in_on_vad_backed_by_transcripts():
    vad, transcript = TurnTakingConfig.from_agent_config({}).start_strategies()

    assert type(vad) is VADUserTurnStartStrategy
    assert type(transcript) is TranscriptFallbackStartStrategy


def test_barge_in_can_be_turned_off():
    config = TurnTakingConfig.from_agent_config(_agent({'barge_in': False}))

    assert config.barge_in is False
    (only,) = config.start_strategies()
    assert isinstance(only, VADWhenBotSilentStartStrategy)
    assert only._start_on_transcript is True


def _discarding_strategy():
    strategy = VADWhenBotSilentStartStrategy(discard_talk_over=True)
    events = []

    async def on_started(*_):
        events.append('turn_started')

    async def on_reset(*_):
        events.append('reset')

    strategy.add_event_handler('on_user_turn_started', on_started)
    strategy.add_event_handler('on_reset_aggregation', on_reset)
    return strategy, events


async def test_talk_over_never_starts_a_turn_and_its_transcript_is_dropped():
    strategy, events = _discarding_strategy()

    await strategy.process_frame(BotStartedSpeakingFrame())
    started = await strategy.process_frame(VADUserStartedSpeakingFrame())
    await strategy.process_frame(
        InterimTranscriptionFrame('hello there', 'u', '', language=None)
    )
    await strategy.process_frame(VADUserStoppedSpeakingFrame())
    await strategy.process_frame(BotStoppedSpeakingFrame())

    assert started == ProcessFrameResult.CONTINUE
    assert events == ['reset']


async def test_user_still_speaking_when_the_bot_finishes_gets_their_turn():
    strategy, events = _discarding_strategy()

    await strategy.process_frame(BotStartedSpeakingFrame())
    await strategy.process_frame(VADUserStartedSpeakingFrame())
    result = await strategy.process_frame(BotStoppedSpeakingFrame())

    assert result == ProcessFrameResult.STOP
    assert events == ['turn_started']


async def test_normal_turns_after_the_bot_finishes_are_unaffected():
    strategy, events = _discarding_strategy()

    await strategy.process_frame(BotStartedSpeakingFrame())
    await strategy.process_frame(BotStoppedSpeakingFrame())
    result = await strategy.process_frame(VADUserStartedSpeakingFrame())

    assert result == ProcessFrameResult.STOP
    assert events == ['turn_started']


def test_zero_words_interrupts_on_vad_alone():
    config = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': True, 'barge_in_min_words': 0})
    )

    assert config.barge_in_min_words == 0
    vad, transcript = config.start_strategies()
    assert type(vad) is VADUserTurnStartStrategy
    assert type(transcript) is TranscriptFallbackStartStrategy


def test_zero_words_does_nothing_while_barge_in_is_off():
    config = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False, 'barge_in_min_words': 0})
    )

    (only,) = config.start_strategies()
    assert isinstance(only, VADWhenBotSilentStartStrategy)


async def test_vad_alone_starts_a_turn_even_while_the_bot_is_speaking():
    strategy = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': True, 'barge_in_min_words': 0})
    ).start_strategies()[0]
    started = []

    async def on_started(*_):
        started.append(True)

    strategy.add_event_handler('on_user_turn_started', on_started)

    await strategy.process_frame(BotStartedSpeakingFrame())
    result = await strategy.process_frame(VADUserStartedSpeakingFrame())

    assert result == ProcessFrameResult.STOP
    assert started == [True]


# ------------------------------------------- transcripts VAD missed (e.g. "Hindi")


def _transcript(text='Hindi.'):
    return TranscriptionFrame(text, 'u', '', language=None)


def _turn_events(strategies):
    events = []

    async def on_started(*_):
        events.append('turn_started')

    async def on_reset(*_):
        events.append('reset')

    for strategy in strategies:
        strategy.add_event_handler('on_user_turn_started', on_started)
        strategy.add_event_handler('on_reset_aggregation', on_reset)
    return events


async def _feed(strategies, frame):
    """As Pipecat does: in order, until a strategy stops the frame."""
    for strategy in strategies:
        if await strategy.process_frame(frame) == ProcessFrameResult.STOP:
            return


def test_transcript_turn_start_is_on_by_default_and_can_be_turned_off():
    assert TurnTakingConfig.from_agent_config({}).transcript_turn_start is True

    config = TurnTakingConfig.from_agent_config(
        _agent({'transcript_turn_start': False})
    )
    (only,) = config.start_strategies()
    assert type(only) is VADUserTurnStartStrategy

    off = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False, 'transcript_turn_start': False})
    )
    assert off.start_strategies()[0]._start_on_transcript is False


def test_non_boolean_transcript_turn_start_falls_back_to_the_default():
    config = TurnTakingConfig.from_agent_config(
        _agent({'transcript_turn_start': 'false'})
    )

    assert config.transcript_turn_start is True


def test_min_words_mode_is_unchanged_by_transcript_turn_start():
    vad_start, min_words = TurnTakingConfig.from_agent_config(
        _agent({'barge_in_min_words': 2})
    ).start_strategies()

    assert vad_start._start_on_transcript is False
    assert isinstance(min_words, MinWordsUserTurnStartStrategy)


async def test_a_transcript_vad_missed_starts_the_turn():
    strategies = TurnTakingConfig.from_agent_config({}).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    await _feed(strategies, _transcript())

    assert events == ['turn_started']


async def test_without_transcript_turn_start_a_missed_word_never_starts_a_turn():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'transcript_turn_start': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStoppedSpeakingFrame())
    await _feed(strategies, _transcript())

    assert events == []


async def test_barge_in_off_starts_a_turn_from_a_transcript_while_the_bot_is_silent():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    await _feed(strategies, _transcript())

    assert events == ['turn_started']


async def test_barge_in_off_still_drops_a_transcript_over_the_bot():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, _transcript('wait'))

    assert events == ['reset']


async def test_barge_in_off_drops_talk_over_transcribed_after_the_bot_stops():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, VADUserStartedSpeakingFrame())
    await _feed(strategies, VADUserStoppedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    # The talk-over's final transcript lands late: dropped, no turn
    await _feed(strategies, _transcript('wait'))
    assert events == ['reset']

    # The next transcript is the user's own answer
    await _feed(strategies, _transcript())
    assert events == ['reset', 'turn_started']


async def test_barge_in_off_a_stale_talk_over_does_not_swallow_a_later_transcript():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    # A noise over the bot that STT never transcribes
    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, VADUserStartedSpeakingFrame())
    await _feed(strategies, VADUserStoppedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    for strategy in strategies:
        if strategy._talk_over_ended_at is not None:
            strategy._talk_over_ended_at -= TALK_OVER_TRANSCRIPT_SECS + 1

    # Later a short reply VAD missed arrives as a transcript alone
    await _feed(strategies, _transcript('Hindi'))

    assert events == ['turn_started']


async def test_barge_in_off_a_new_bot_turn_clears_a_pending_talk_over():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, VADUserStartedSpeakingFrame())
    await _feed(strategies, VADUserStoppedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, BotStoppedSpeakingFrame())
    await _feed(strategies, _transcript('Hindi'))

    assert events == ['turn_started']


# ------------------------------------------------------ mute until first bot speech


def test_welcome_mute_is_off_by_default():
    config = TurnTakingConfig.from_agent_config({})

    assert config.mute_until_first_bot_complete is False
    assert [type(s).__name__ for s in config.mute_strategies(will_greet=True)] == [
        'FunctionCallUserMuteStrategy'
    ]


def test_welcome_mute_needs_a_greeting_to_wait_for():
    config = TurnTakingConfig.from_agent_config(
        _agent({'mute_until_first_bot_complete': True})
    )

    assert config.mute_until_first_bot_complete is True
    assert [type(s).__name__ for s in config.mute_strategies(will_greet=True)] == [
        'MuteUntilFirstBotCompleteUserMuteStrategy',
        'FunctionCallUserMuteStrategy',
    ]
    assert [type(s).__name__ for s in config.mute_strategies(will_greet=False)] == [
        'FunctionCallUserMuteStrategy'
    ]


def test_non_boolean_welcome_mute_falls_back_to_the_default():
    config = TurnTakingConfig.from_agent_config(
        _agent({'mute_until_first_bot_complete': 'true'})
    )

    assert config.mute_until_first_bot_complete is False


# --------------------------------- transcript turn starts that must not interrupt


def _interim(text='Hin'):
    return InterimTranscriptionFrame(text, 'u', '', language=None)


def _just_after_a_turn(strategies):
    """As if a user turn had just ended (the controller tells every strategy)."""
    for strategy in strategies:
        strategy._turn_stopped_at = time.monotonic()


def _long_after_a_turn(strategies):
    for strategy in strategies:
        strategy._turn_stopped_at = time.monotonic() - LATE_TRANSCRIPT_SECS - 1


async def test_an_interim_transcript_never_starts_a_turn():
    strategies = TurnTakingConfig.from_agent_config({}).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStartedSpeakingFrame())
    await _feed(strategies, _interim())

    assert events == []


async def test_a_final_landing_just_after_a_turn_ended_does_not_interrupt():
    strategies = TurnTakingConfig.from_agent_config({}).start_strategies()
    events = _turn_events(strategies)

    _just_after_a_turn(strategies)
    await _feed(strategies, _transcript('and the rest of it'))
    # No turn, and no reset: the text joins the next turn rather than being lost
    assert events == []

    _long_after_a_turn(strategies)
    await _feed(strategies, _transcript())
    assert events == ['turn_started']


async def test_the_turn_end_is_recorded_from_the_controller_callback():
    strategy = TranscriptFallbackStartStrategy()
    assert strategy._transcript_is_late() is False

    await strategy.handle_user_turn_stopped()

    assert strategy._transcript_is_late() is True


async def test_barge_in_off_ignores_a_final_landing_just_after_a_turn_ended():
    strategies = TurnTakingConfig.from_agent_config(
        _agent({'barge_in': False})
    ).start_strategies()
    events = _turn_events(strategies)

    await _feed(strategies, BotStoppedSpeakingFrame())
    _just_after_a_turn(strategies)
    await _feed(strategies, _transcript('and the rest of it'))
    # No turn, and no reset: the text joins the next turn rather than being lost
    assert events == []

    _long_after_a_turn(strategies)
    await _feed(strategies, _transcript())
    assert events == ['turn_started']
