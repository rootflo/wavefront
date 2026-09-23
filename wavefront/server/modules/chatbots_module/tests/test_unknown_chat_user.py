"""A credential can authenticate without corresponding to a wavefront user.

A floconsole token carries a user id from the console's own database: a valid
uuid, so it passes the auth helper, but with no matching row in wavefront's
`user` table. chat_sessions.user_id is a NOT NULL foreign key to that table, so
the insert fails -- and must fail as a 403, not an uncaught IntegrityError.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from db_repo_module.models.chat_message import ChatMessage
from sqlalchemy.exc import IntegrityError

from chatbots_module.services.chat_session_service import (
    ChatSessionService,
    UnknownChatUserError,
)

from fakes import FakeDbSession, repository_with_session


def _chatbot(welcome_message=None):
    return SimpleNamespace(
        id=uuid.uuid4(), system_prompt='p', welcome_message=welcome_message
    )


def _service(db: FakeDbSession) -> ChatSessionService:
    return ChatSessionService(
        chat_session_repository=repository_with_session(db),
        chat_message_repository=AsyncMock(),
    )


def _fk_violation() -> IntegrityError:
    return IntegrityError(
        'INSERT INTO chat_sessions', {}, Exception('violates foreign key constraint')
    )


async def test_foreign_key_violation_becomes_a_domain_error():
    db = FakeDbSession(commit_error=_fk_violation())

    with pytest.raises(UnknownChatUserError):
        await _service(db).create_session(chatbot=_chatbot(), user_id=uuid.uuid4())


async def test_a_violation_raised_at_flush_is_handled_too():
    # The realistic failure point: the INSERT reaches the server at flush, so
    # Postgres rejects the foreign key there rather than at commit. Guards
    # against the try/except ever being narrowed to just the commit call.
    db = FakeDbSession(flush_error=_fk_violation())

    with pytest.raises(UnknownChatUserError):
        await _service(db).create_session(chatbot=_chatbot(), user_id=uuid.uuid4())

    assert db.commits == 0


async def test_error_names_the_rejected_user_id():
    user_id = uuid.uuid4()
    db = FakeDbSession(commit_error=_fk_violation())

    with pytest.raises(UnknownChatUserError, match=str(user_id)):
        await _service(db).create_session(chatbot=_chatbot(), user_id=user_id)


async def test_nothing_is_persisted_when_the_session_fails():
    # The welcome message is staged in the same transaction, so a rejected
    # commit must leave neither row -- otherwise each retry of a failing create
    # would strand another empty thread.
    db = FakeDbSession(commit_error=_fk_violation())

    with pytest.raises(UnknownChatUserError):
        await _service(db).create_session(
            chatbot=_chatbot(welcome_message='Hello'), user_id=uuid.uuid4()
        )

    assert db.commits == 0
    assert db.rolled_back
    # Staged alongside the session, never committed on its own.
    assert len(db.added_of(ChatMessage)) == 1
