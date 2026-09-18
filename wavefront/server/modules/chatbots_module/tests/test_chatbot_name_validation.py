"""Chatbot names are identifiers, anchored with \\Z rather than $.

Python's `$` also matches immediately before a trailing newline, so
`support-bot\\n` passed the old pattern. It would then be stored as a row
distinct from `support-bot` while rendering identically in the console -- two
chatbots that look the same, which the partial unique index cannot tell apart
because the stored values genuinely differ.

The equivalent zod pattern on the client is already strict: JavaScript's `$`
only matches before a trailing newline under the `m` flag, which it does not
set.
"""

import uuid

import pytest
from pydantic import ValidationError

from chatbots_module.models.chatbot_schemas import (
    CreateChatbotPayload,
    UpdateChatbotPayload,
)


def _create(name: str) -> CreateChatbotPayload:
    return CreateChatbotPayload(
        name=name,
        system_prompt='be helpful',
        llm_config_id=uuid.uuid4(),
    )


@pytest.mark.parametrize(
    'name', ['supportbot', 'support-bot', 'support_bot', 'Bot1', 'a']
)
def test_valid_identifiers_are_accepted(name):
    assert _create(name).name == name


def test_a_trailing_newline_is_rejected():
    # The regression: accepted under `$`, rejected under `\Z`.
    with pytest.raises(ValidationError):
        _create('support-bot\n')


@pytest.mark.parametrize(
    'name',
    [
        'support-bot\r\n',
        'support-bot\n\n',
        'support\nbot',  # embedded, rejected by either anchor
        'support bot',
        '1bot',  # must start with a letter
        '-bot',
        'bot!',
        '',
    ],
)
def test_invalid_names_are_rejected(name):
    with pytest.raises(ValidationError):
        _create(name)


def test_the_update_payload_applies_the_same_rule():
    # Renaming must not be a way around the create-time check.
    with pytest.raises(ValidationError):
        UpdateChatbotPayload(name='support-bot\n')


def test_the_update_payload_still_allows_an_absent_name():
    # Every field is optional on update; only a supplied name is validated.
    assert UpdateChatbotPayload(enabled=True).name is None
