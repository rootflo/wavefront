from pipecat.turns.user_start import MinWordsUserTurnStartStrategy

from call_processing.services.smart_turn import SharedSmartTurnAnalyzer
from call_processing.services.turn_taking import (
    TurnTakingConfig,
    VADWhenBotSilentStartStrategy,
)


def _agent(turn_taking):
    return {'conversation_config': {'turn_taking': turn_taking}}


def test_agent_without_turn_taking_config_gets_defaults():
    config = TurnTakingConfig.from_agent_config({})

    assert config == TurnTakingConfig()
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
                'barge_in_min_words': 3,
                'vad_confidence': 0.8,
                'vad_min_volume': 0.5,
                'vad_start_ms': 150,
                'vad_stop_ms': 300,
                'end_of_turn_timeout_ms': 2000,
            }
        )
    )

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
                'barge_in_min_words': 0,
                'vad_confidence': 5,
                'vad_stop_ms': 'fast',
                'end_of_turn_timeout_ms': True,
            }
        )
    )

    assert config.barge_in_min_words == 1
    assert config.vad_confidence == 0.95
    assert config.vad_stop_secs == 0.2
    assert config.end_of_turn_timeout_secs == 3.0


def test_strategies_carry_the_agent_settings():
    config = TurnTakingConfig.from_agent_config(
        _agent({'barge_in_min_words': 4, 'end_of_turn_timeout_ms': 1500})
    )

    vad_start, min_words = config.start_strategies()
    assert isinstance(vad_start, VADWhenBotSilentStartStrategy)
    assert isinstance(min_words, MinWordsUserTurnStartStrategy)
    assert min_words._min_words == 4

    (stop,) = config.stop_strategies()
    analyzer = stop._turn_analyzer
    assert isinstance(analyzer, SharedSmartTurnAnalyzer)
    assert analyzer.params.stop_secs == 1.5
