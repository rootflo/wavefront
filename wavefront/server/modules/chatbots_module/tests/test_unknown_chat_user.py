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
from sqlalchemy.exc import IntegrityError

from chatbots_module.services.chat_session_service import (
    ChatSessionService,
    UnknownChatUserError,
)


def _chatbot():
    return SimpleNamespace(id=uuid.uuid4(), system_prompt='p', welcome_message=None)


async def test_foreign_key_violation_becomes_a_domain_error():
    session_repo = AsyncMock()
    session_repo.create.side_effect = IntegrityError(
        'INSERT INTO chat_sessions', {}, Exception('violates foreign key constraint')
    )
    service = ChatSessionService(
        chat_session_repository=session_repo,
        chat_message_repository=AsyncMock(),
    )

    with pytest.raises(UnknownChatUserError):
        await service.create_session(chatbot=_chatbot(), user_id=uuid.uuid4())


async def test_error_names_the_rejected_user_id():
    user_id = uuid.uuid4()
    session_repo = AsyncMock()
    session_repo.create.side_effect = IntegrityError('stmt', {}, Exception('fk'))
    service = ChatSessionService(
        chat_session_repository=session_repo,
        chat_message_repository=AsyncMock(),
    )

    with pytest.raises(UnknownChatUserError, match=str(user_id)):
        await service.create_session(chatbot=_chatbot(), user_id=user_id)


async def test_no_welcome_message_is_written_when_the_session_fails():
    # The welcome insert must not run against a session id that was rolled back.
    session_repo = AsyncMock()
    session_repo.create.side_effect = IntegrityError('stmt', {}, Exception('fk'))
    message_repo = AsyncMock()
    chatbot = SimpleNamespace(
        id=uuid.uuid4(), system_prompt='p', welcome_message='Hello'
    )
    service = ChatSessionService(
        chat_session_repository=session_repo,
        chat_message_repository=message_repo,
    )

    with pytest.raises(UnknownChatUserError):
        await service.create_session(chatbot=chatbot, user_id=uuid.uuid4())

    message_repo.create.assert_not_awaited()
