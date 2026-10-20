from call_processing.services.conversation_completion_tool import (
    DEFAULT_FAREWELL,
    EndConversationConfig,
)


def _config(section):
    return EndConversationConfig.from_agent_config(
        {'conversation_config': {'end_conversation': section}}
    )


def test_off_with_default_farewell_when_unset():
    config = EndConversationConfig.from_agent_config({})

    assert config.enabled is False
    assert config.farewell_message == DEFAULT_FAREWELL


def test_enabled_with_custom_farewell():
    config = _config({'enabled': True, 'farewell_message': '  Take care!  '})

    assert config.enabled is True
    assert config.farewell_message == 'Take care!'


def test_only_a_real_true_enables_it():
    for value in ('true', 1, 'yes', None):
        assert _config({'enabled': value}).enabled is False


def test_blank_or_non_string_farewell_falls_back_to_default():
    for value in ('', '   ', 5, None):
        assert _config(
            {'enabled': True, 'farewell_message': value}
        ).farewell_message == (DEFAULT_FAREWELL)
