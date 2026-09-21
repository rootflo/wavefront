"""Guards the schema invariant that makes a sequence-less chat_messages safe.

Ordering is `created_at` alone. That only works while two rows written for one
turn get distinct timestamps, which in turn requires the default to be evaluated
per row in Python. Switching it to `func.now()` or adding a `server_default`
would give every row in a transaction the same statement timestamp and make the
order of a turn arbitrary -- a bug that shows up as a conversation rendering its
answer above its question, intermittently.
"""

from datetime import datetime, timezone

from db_repo_module.models.chat_message import ChatMessage


def _created_at_column():
    return ChatMessage.__table__.columns['created_at']


def test_created_at_default_is_a_python_callable():
    default = _created_at_column().default
    assert default is not None, 'created_at must have a default'
    assert default.is_callable, (
        'created_at must use a Python-side callable default so each row gets '
        'its own timestamp; a SQL default would be identical across a transaction'
    )


def test_created_at_has_no_server_default():
    assert _created_at_column().server_default is None, (
        'a server_default would apply the statement timestamp and collide '
        'rows written in the same transaction'
    )


def test_created_at_default_is_timezone_aware_and_advances():
    default = _created_at_column().default
    first = default.arg({})
    second = default.arg({})

    assert first.tzinfo is not None, 'created_at must be timezone-aware'
    assert second >= first
    assert isinstance(first, datetime)


def test_created_at_is_utc():
    default = _created_at_column().default
    assert default.arg({}).tzinfo is timezone.utc


def test_no_updated_at_column():
    # Messages are immutable; an updated_at would imply otherwise.
    assert 'updated_at' not in ChatMessage.__table__.columns
