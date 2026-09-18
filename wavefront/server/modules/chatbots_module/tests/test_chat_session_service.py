import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession

from chatbots_module.services.chat_session_service import (
    ChatSessionNotFoundError,
    ChatSessionService,
)
from chatbots_module.utils.constants import ROLE_ASSISTANT

from .fakes import FakeDbSession, repository_with_session


def _service(session_repo=None, message_repo=None):
    return ChatSessionService(
        chat_session_repository=session_repo or AsyncMock(),
        chat_message_repository=message_repo or AsyncMock(),
    )


class TestOwnership:
    """A session belonging to someone else must be indistinguishable from one
    that does not exist. A 403 would confirm the id is real and turn session ids
    into an enumerable directory.
    """

    async def test_returns_session_for_its_owner(self):
        owner = uuid.uuid4()
        stored = SimpleNamespace(id=uuid.uuid4(), user_id=owner)
        repo = AsyncMock()
        repo.find_one.return_value = stored

        assert await _service(repo).get_owned_session(stored.id, owner) is stored

    async def test_another_users_session_raises_not_found(self):
        stored = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        repo = AsyncMock()
        repo.find_one.return_value = stored

        with pytest.raises(ChatSessionNotFoundError):
            await _service(repo).get_owned_session(stored.id, uuid.uuid4())

    async def test_missing_session_raises_not_found(self):
        repo = AsyncMock()
        repo.find_one.return_value = None

        with pytest.raises(ChatSessionNotFoundError):
            await _service(repo).get_owned_session(uuid.uuid4(), uuid.uuid4())

    async def test_lookup_excludes_soft_deleted(self):
        repo = AsyncMock()
        repo.find_one.return_value = None
        session_id = uuid.uuid4()

        with pytest.raises(ChatSessionNotFoundError):
            await _service(repo).get_owned_session(session_id, uuid.uuid4())

        repo.find_one.assert_awaited_once_with(id=session_id, is_deleted=False)


class TestPromptSnapshot:
    """The session row and its welcome message share one transaction.

    Asserted through a fake unit of work rather than on repository calls: the
    point of the design is that both writes go through a single session, so a
    failed welcome cannot leave a stranded thread behind.
    """

    async def test_session_pins_the_chatbots_current_prompt(self):
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='be terse', welcome_message=None
        )
        db = FakeDbSession()
        user_id = uuid.uuid4()

        await _service(repository_with_session(db)).create_session(
            chatbot=chatbot, user_id=user_id
        )

        (session,) = db.added_of(ChatSession)
        assert session.system_prompt_snapshot == 'be terse'
        assert session.chatbot_id == chatbot.id
        assert session.user_id == user_id
        assert session.title is None
        assert db.commits == 1

    async def test_welcome_message_is_stored_as_the_first_assistant_turn(self):
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='p', welcome_message='Hi there'
        )
        db = FakeDbSession()

        await _service(repository_with_session(db)).create_session(
            chatbot=chatbot, user_id=uuid.uuid4()
        )

        (session,) = db.added_of(ChatSession)
        (message,) = db.added_of(ChatMessage)
        assert message.role == ROLE_ASSISTANT
        assert message.content == 'Hi there'
        assert message.session_id == session.id

    async def test_both_rows_are_committed_together(self):
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='p', welcome_message='Hi there'
        )
        db = FakeDbSession()
        repository = repository_with_session(db)

        await _service(repository).create_session(chatbot=chatbot, user_id=uuid.uuid4())

        # One session, one commit: two commits would mean the old behaviour,
        # where a failed welcome insert left the thread behind.
        assert repository.session.call_count == 1
        assert db.commits == 1

    async def test_blank_welcome_message_is_not_stored(self):
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='p', welcome_message='   '
        )
        db = FakeDbSession()

        await _service(repository_with_session(db)).create_session(
            chatbot=chatbot, user_id=uuid.uuid4()
        )

        assert db.added_of(ChatMessage) == []

    async def test_the_returned_session_is_refreshed(self):
        # expire_on_commit is on, so without the refresh the controller would
        # read a detached row with every attribute expired.
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='p', welcome_message=None
        )
        db = FakeDbSession()

        session = await _service(repository_with_session(db)).create_session(
            chatbot=chatbot, user_id=uuid.uuid4()
        )

        assert db.refreshed == [session]


class TestEnsureTitle:
    async def test_derives_title_from_the_first_message(self):
        repo = AsyncMock()
        session = SimpleNamespace(id=uuid.uuid4(), title=None)

        await _service(repo).ensure_title(session, '  How   do I reset  my password? ')

        _, kwargs = repo.find_one_and_update.await_args
        assert kwargs['title'] == 'How do I reset my password?'

    async def test_truncates_to_the_configured_length(self):
        repo = AsyncMock()
        session = SimpleNamespace(id=uuid.uuid4(), title=None)

        await _service(repo).ensure_title(session, 'x' * 200)

        _, kwargs = repo.find_one_and_update.await_args
        assert len(kwargs['title']) == 60

    async def test_existing_title_is_left_alone(self):
        repo = AsyncMock()
        session = SimpleNamespace(id=uuid.uuid4(), title='Chosen by the user')

        await _service(repo).ensure_title(session, 'something else')

        repo.find_one_and_update.assert_not_awaited()
