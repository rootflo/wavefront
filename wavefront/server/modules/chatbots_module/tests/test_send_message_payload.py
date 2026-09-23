"""`content` is bounded at the API boundary.

Without a cap, a client can POST an arbitrarily large string: it is written to
a Text column (Postgres accepts ~1GB) and only then refused by the provider, so
the insert and the round trip are both paid for before the refusal arrives.

Note what this does NOT bound: MAX_HISTORY_MESSAGES turns of this length
together exceed every provider's context window. That case still surfaces as a
provider error, because bounding a whole request needs a per-provider token
count that does not exist here -- see utils/constants.py.
"""

import pytest
from pydantic import ValidationError

from chatbots_module.models.chat_schemas import SendMessagePayload
from chatbots_module.utils.constants import MAX_MESSAGE_LENGTH


def test_a_normal_message_is_accepted():
    payload = SendMessagePayload(content='How do I reset my password?')
    assert payload.content == 'How do I reset my password?'


def test_a_message_at_the_limit_is_accepted():
    content = 'x' * MAX_MESSAGE_LENGTH
    assert SendMessagePayload(content=content).content == content


def test_a_message_over_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        SendMessagePayload(content='x' * (MAX_MESSAGE_LENGTH + 1))


def test_whitespace_only_is_still_rejected():
    # The length cap must not displace the emptiness check.
    for value in ['', '   ', '\n\t ']:
        with pytest.raises(ValidationError):
            SendMessagePayload(content=value)


def test_content_is_not_stripped():
    # Only validated, never rewritten: leading newlines in a pasted excerpt are
    # the user's formatting and reach the model as written.
    payload = SendMessagePayload(content='  spaced  ')
    assert payload.content == '  spaced  '


def test_the_limit_is_generous_enough_to_be_usable():
    # A guard against someone "tightening" this to a value that breaks pasting
    # a document excerpt, which is a normal thing to do in a chat.
    assert MAX_MESSAGE_LENGTH >= 10000
