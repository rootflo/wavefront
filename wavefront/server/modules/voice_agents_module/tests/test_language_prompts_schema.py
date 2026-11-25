"""conversation_config.language_prompts validation. Made-up packs only."""

import pytest
from pydantic import ValidationError

from voice_agents_module.models.voice_agent_schemas import (
    MAX_LANGUAGE_PROMPT_CHARS,
    UpdateVoiceAgentPayload,
    check_language_prompts,
)


def test_valid_packs_pass():
    check_language_prompts(
        {'language_prompts': {'ta': 'Tamil rules'}, 'filler_speech': {}}, ['en', 'ta']
    )


def test_no_packs_or_no_config_pass():
    check_language_prompts({'filler_speech': {}}, ['en'])
    check_language_prompts(None, ['en'])


@pytest.mark.parametrize(
    'packs, supported, message',
    [
        (['ta'], ['en', 'ta'], 'must be an object'),
        ({'ta': 42}, ['en', 'ta'], 'must be text'),
        ({'ta': 'x' * (MAX_LANGUAGE_PROMPT_CHARS + 1)}, ['en', 'ta'], 'characters'),
        ({'fr': 'French rules'}, ['en', 'ta'], 'does not support'),
    ],
)
def test_bad_packs_are_rejected(packs, supported, message):
    with pytest.raises(ValueError, match=message):
        check_language_prompts({'language_prompts': packs}, supported)


def test_update_without_languages_checks_shape_only():
    # Languages are not in this update, so membership can't be checked here
    payload = UpdateVoiceAgentPayload(
        conversation_config={'language_prompts': {'fr': 'French rules'}}
    )
    assert payload.conversation_config['language_prompts'] == {'fr': 'French rules'}

    with pytest.raises(ValidationError):
        UpdateVoiceAgentPayload(conversation_config={'language_prompts': {'ta': 1}})


def test_update_with_languages_checks_membership():
    with pytest.raises(ValidationError):
        UpdateVoiceAgentPayload(
            supported_languages=['en'],
            conversation_config={'language_prompts': {'ta': 'Tamil rules'}},
        )
