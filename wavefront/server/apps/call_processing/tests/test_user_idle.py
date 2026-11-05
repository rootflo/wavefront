from call_processing.services.common.turn_taking import TurnTakingConfig
from call_processing.services.common.user_idle import (
    DEFAULT_IDLE_GOODBYE,
    MAX_IDLE_GOODBYES,
    IdleAction,
    IdleCheckIns,
)


def _config(turn_taking):
    return TurnTakingConfig.from_agent_config(
        {'conversation_config': {'turn_taking': turn_taking}}
    )


# ------------------------------------------------------------------ config


def test_idle_check_ins_are_off_by_default_with_an_llm_goodbye():
    config = TurnTakingConfig.from_agent_config({})

    assert config.idle_timeout_secs == 0
    assert config.idle_max_check_ins == 2
    assert config.idle_fixed_goodbye is False
    assert config.idle_goodbye_message == DEFAULT_IDLE_GOODBYE


def test_idle_settings_are_read_from_turn_taking():
    config = _config(
        {
            'idle_timeout_ms': 8000,
            'idle_max_check_ins': 3,
            'idle_fixed_goodbye': True,
            'idle_goodbye_message': '  Bye for now!  ',
        }
    )

    assert config.idle_timeout_secs == 8.0
    assert config.idle_max_check_ins == 3
    assert config.idle_fixed_goodbye is True
    assert config.idle_goodbye_message == 'Bye for now!'


def test_idle_numbers_are_clamped_and_junk_is_ignored():
    assert _config({'idle_timeout_ms': 0}).idle_timeout_secs == 0
    # Non-zero but tiny would check in on every breath
    assert _config({'idle_timeout_ms': 300}).idle_timeout_secs == 2.0
    assert _config({'idle_timeout_ms': 999999}).idle_timeout_secs == 60.0
    assert _config({'idle_timeout_ms': -5}).idle_timeout_secs == 0
    assert _config({'idle_timeout_ms': 'soon'}).idle_timeout_secs == 0
    assert _config({'idle_max_check_ins': 50}).idle_max_check_ins == 5
    assert _config({'idle_max_check_ins': -1}).idle_max_check_ins == 0
    assert _config({'idle_max_check_ins': True}).idle_max_check_ins == 2


def test_only_a_real_true_fixes_the_goodbye():
    for value in ('true', 1, 'yes', None):
        assert _config({'idle_fixed_goodbye': value}).idle_fixed_goodbye is False


def test_blank_or_non_string_goodbye_falls_back_to_default():
    for value in ('', '   ', 5, None):
        assert _config({'idle_goodbye_message': value}).idle_goodbye_message == (
            DEFAULT_IDLE_GOODBYE
        )


# ------------------------------------------------------------- check-ins


def _silent_through_check_ins(check_ins, count):
    for _ in range(count):
        assert check_ins.on_idle() is IdleAction.CHECK_IN


def test_checks_in_max_times_then_asks_the_llm_for_a_goodbye():
    check_ins = IdleCheckIns(max_check_ins=2)
    _silent_through_check_ins(check_ins, 2)

    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE
    # The goodbye was spoken in full: end the call, once
    assert check_ins.assistant_turn_stopped(interrupted=False) is True
    assert check_ins.on_idle() is None
    assert check_ins.assistant_turn_stopped(interrupted=False) is False


def test_a_silent_turn_is_not_the_goodbye():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()
    goodbye_id = check_ins.goodbye_id

    # e.g. the LLM answered the goodbye prompt with only a tool call
    assert check_ins.assistant_turn_stopped(interrupted=False, spoke=False) is False
    # Still pending: the spoken goodbye that follows ends the call
    assert check_ins.assistant_turn_stopped(interrupted=False) is True
    assert check_ins.goodbye_overdue(goodbye_id) is False


def test_a_goodbye_that_never_speaks_is_overdue():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()

    check_ins.assistant_turn_stopped(interrupted=False, spoke=False)

    assert check_ins.goodbye_overdue(check_ins.goodbye_id) is True


def test_check_in_replies_do_not_end_the_call():
    check_ins = IdleCheckIns(max_check_ins=2)
    check_ins.on_idle()

    assert check_ins.assistant_turn_stopped(interrupted=False) is False


def test_fixed_goodbye_ends_the_call_without_asking_the_llm():
    check_ins = IdleCheckIns(max_check_ins=1, fixed_goodbye=True)
    _silent_through_check_ins(check_ins, 1)

    assert check_ins.on_idle() is IdleAction.FIXED_GOODBYE
    # Speaking the fixed goodbye is an assistant turn too; already ending
    assert check_ins.assistant_turn_stopped(interrupted=False) is False
    assert check_ins.on_idle() is None


def test_zero_check_ins_says_goodbye_on_first_silence():
    assert IdleCheckIns(max_check_ins=0).on_idle() is IdleAction.SAY_GOODBYE


def test_transcribed_words_reset_the_count():
    check_ins = IdleCheckIns(max_check_ins=2)
    _silent_through_check_ins(check_ins, 2)

    check_ins.user_spoke('yes, still here')

    _silent_through_check_ins(check_ins, 2)
    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE


def test_noise_without_a_transcript_does_not_reset_the_count():
    check_ins = IdleCheckIns(max_check_ins=1)
    check_ins.on_idle()

    for transcript in ('', '   ', None):
        check_ins.user_spoke(transcript)

    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE


def test_an_interrupted_goodbye_is_called_off_and_asked_for_again():
    check_ins = IdleCheckIns(max_check_ins=0)
    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE

    # Noise cut the goodbye off: no hang-up, and no reset of the count
    assert check_ins.assistant_turn_stopped(interrupted=True) is False
    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE


def test_noise_cutting_off_every_goodbye_still_ends_the_call():
    check_ins = IdleCheckIns(max_check_ins=0)
    for _ in range(MAX_IDLE_GOODBYES):
        assert check_ins.on_idle() is IdleAction.SAY_GOODBYE
        check_ins.assistant_turn_stopped(interrupted=True)
        check_ins.user_spoke('')

    assert check_ins.on_idle() is IdleAction.HANG_UP
    assert check_ins.on_idle() is None


def test_words_reset_the_goodbye_limit():
    check_ins = IdleCheckIns(max_check_ins=0)
    for _ in range(MAX_IDLE_GOODBYES):
        check_ins.on_idle()
        check_ins.assistant_turn_stopped(interrupted=True)

    check_ins.user_spoke('sorry, I am back')

    assert check_ins.on_idle() is IdleAction.SAY_GOODBYE


def test_words_during_the_goodbye_keep_the_call_going():
    check_ins = IdleCheckIns(max_check_ins=1)
    _silent_through_check_ins(check_ins, 1)
    check_ins.on_idle()

    check_ins.assistant_turn_stopped(interrupted=True)
    check_ins.user_spoke('wait, I am here')

    assert check_ins.on_idle() is IdleAction.CHECK_IN


def test_goodbye_that_never_finishes_hangs_up_on_the_next_silence():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()

    assert check_ins.on_idle() is IdleAction.HANG_UP
    assert check_ins.on_idle() is None


def test_overdue_goodbye_ends_the_call_once():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()
    goodbye_id = check_ins.goodbye_id

    assert check_ins.goodbye_overdue(goodbye_id) is True
    assert check_ins.goodbye_overdue(goodbye_id) is False
    assert check_ins.on_idle() is None


def test_spoken_goodbye_is_not_overdue():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()
    goodbye_id = check_ins.goodbye_id
    check_ins.assistant_turn_stopped(interrupted=False)

    assert check_ins.goodbye_overdue(goodbye_id) is False


def test_stale_grace_timer_ignores_a_later_goodbye():
    check_ins = IdleCheckIns(max_check_ins=0)
    check_ins.on_idle()
    first_id = check_ins.goodbye_id
    check_ins.assistant_turn_stopped(interrupted=True)
    check_ins.on_idle()

    assert check_ins.goodbye_overdue(first_id) is False
    assert check_ins.goodbye_overdue(check_ins.goodbye_id) is True
