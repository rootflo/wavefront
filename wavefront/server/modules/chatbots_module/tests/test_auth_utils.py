"""`request.state.session.user_id` arrives as a raw JWT claim -- a str.

chat_sessions.user_id is a uuid column, so a str would never compare equal to a
loaded session's user_id and every owned-session lookup would 404. Service
identities carry non-uuid sentinels ('service', 'hmac-service', ...) that no
`user` row can match, so they are rejected rather than coerced.
"""

import uuid
from types import SimpleNamespace

import pytest

from chatbots_module.utils.auth_utils import NotAUserError, current_user_id


def _request(user_id):
    return SimpleNamespace(
        state=SimpleNamespace(session=SimpleNamespace(user_id=user_id))
    )


def test_string_claim_is_parsed_to_uuid():
    expected = uuid.uuid4()
    resolved = current_user_id(_request(str(expected)))
    assert resolved == expected
    assert isinstance(resolved, uuid.UUID)


def test_uuid_claim_passes_through():
    expected = uuid.uuid4()
    assert current_user_id(_request(expected)) == expected


@pytest.mark.parametrize(
    'sentinel', ['service', 'passthrough', 'hmac-service', '', None]
)
def test_service_identities_are_rejected(sentinel):
    with pytest.raises(NotAUserError):
        current_user_id(_request(sentinel))
