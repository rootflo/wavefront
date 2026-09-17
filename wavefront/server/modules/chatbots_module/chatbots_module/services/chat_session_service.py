import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chatbots_module.utils.constants import (
    MAX_HISTORY_MESSAGES,
    ROLE_ASSISTANT,
    TITLE_MAX_LENGTH,
)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Treat a naive pagination cursor as UTC.

    created_at is timestamptz; comparing it against a naive datetime from a
    query string would otherwise be interpreted in the server's timezone and
    silently skip or repeat rows near the boundary.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class ChatSessionNotFoundError(Exception):
    """Also raised when a session exists but belongs to someone else.

    Callers must surface this as 404, never 403: a 403 confirms the id is real
    and turns session ids into an enumerable directory.
    """


class UnknownChatUserError(Exception):
    """The caller's user id does not exist in wavefront's `user` table.

    Reachable with a credential that authenticates elsewhere: a floconsole
    token carries a user id from the console's own database, which is a valid
    uuid but has no matching row here. Without this, the foreign key rejects
    the insert and the caller gets a 500.
    """


class ChatSessionService:
    def __init__(
        self,
        chat_session_repository: SQLAlchemyRepository[ChatSession],
        chat_message_repository: SQLAlchemyRepository[ChatMessage],
    ):
        self.chat_session_repository = chat_session_repository
        self.chat_message_repository = chat_message_repository

    async def create_session(
        self,
        chatbot: Chatbot,
        user_id: uuid.UUID,
        title: Optional[str] = None,
    ) -> ChatSession:
        """Open a thread, pinning the chatbot's current prompt to it.

        The snapshot is what makes an old conversation explainable: editing
        `chatbots.system_prompt` afterwards must not retroactively change the
        premise of replies that were already given.
        """
        try:
            session = await self.chat_session_repository.create(
                chatbot_id=chatbot.id,
                user_id=user_id,
                title=title,
                system_prompt_snapshot=chatbot.system_prompt,
            )
        except IntegrityError as exc:
            # The only foreign key that can fail here is user_id -> user.id;
            # chatbot_id was just read successfully. Let the constraint be the
            # authority rather than pre-checking the user table on every create.
            raise UnknownChatUserError(
                f'No wavefront user exists for id {user_id}'
            ) from exc

        # Stored rather than returned-and-forgotten so a reloaded thread renders
        # identically, and so the model sees what it already "said".
        if chatbot.welcome_message and chatbot.welcome_message.strip():
            await self.add_message(
                session_id=session.id,
                role=ROLE_ASSISTANT,
                content=chatbot.welcome_message,
            )

        return session

    async def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession:
        """Load a session, enforcing ownership in the same step.

        Every route that touches a session must go through here -- an ownership
        check that lives in the caller is one a future route will forget.
        """
        session = await self.chat_session_repository.find_one(
            id=session_id, is_deleted=False
        )
        if not session or session.user_id != user_id:
            raise ChatSessionNotFoundError(f'Chat session not found: {session_id}')
        return session

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        chatbot_id: Optional[uuid.UUID] = None,
        cursor: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[ChatSession]:
        """Newest first, keyed on created_at.

        Sessions sort by when they were opened, not by last activity -- there is
        deliberately no last_message_at, and `updated_at` tracks row edits only.

        Needs a hand-written select because SQLAlchemyRepository.find() supports
        equality filters only, and `created_at < cursor` is a range predicate.
        """
        async with self.chat_session_repository.session() as db_session:
            query = (
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .where(ChatSession.is_deleted.is_(False))
            )
            if chatbot_id is not None:
                query = query.where(ChatSession.chatbot_id == chatbot_id)
            cursor = _as_utc(cursor)
            if cursor is not None:
                query = query.where(ChatSession.created_at < cursor)

            query = query.order_by(ChatSession.created_at.desc()).limit(limit)
            return list((await db_session.scalars(query)).all())

    async def update_title(
        self, session_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> ChatSession:
        await self.get_owned_session(session_id, user_id)
        updated = await self.chat_session_repository.find_one_and_update(
            {'id': session_id, 'is_deleted': False}, refresh=True, title=title
        )
        if not updated:
            raise ChatSessionNotFoundError(f'Chat session not found: {session_id}')
        return updated

    async def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.get_owned_session(session_id, user_id)
        await self.chat_session_repository.find_one_and_update(
            {'id': session_id, 'is_deleted': False}, is_deleted=True
        )

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ChatMessage:
        """Insert one message and commit it on its own.

        Each turn is committed separately on purpose. `chat_messages` has no
        sequence column, so ordering rests on `created_at` being distinct; two
        rows batched into one transaction would take the same timestamp and the
        turn would render in arbitrary order. Committing the user's message
        before inference also means it survives an LLM failure.
        """
        return await self.chat_message_repository.create(
            session_id=session_id,
            role=role,
            content=content,
            metadata_=metadata,
        )

    async def get_history(
        self, session_id: uuid.UUID, limit: int = MAX_HISTORY_MESSAGES
    ) -> list[ChatMessage]:
        """The newest `limit` messages, returned oldest-first.

        Selected descending then reversed: taking the *newest* N needs a
        descending scan, but the model needs them chronologically.
        """
        async with self.chat_message_repository.session() as db_session:
            query = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
            messages = list((await db_session.scalars(query)).all())
        messages.reverse()
        return messages

    async def list_messages(
        self,
        session_id: uuid.UUID,
        cursor: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """A page of messages in send order, for rendering a thread."""
        async with self.chat_message_repository.session() as db_session:
            query = select(ChatMessage).where(ChatMessage.session_id == session_id)
            cursor = _as_utc(cursor)
            if cursor is not None:
                query = query.where(ChatMessage.created_at > cursor)
            query = query.order_by(ChatMessage.created_at.asc()).limit(limit)
            return list((await db_session.scalars(query)).all())

    async def ensure_title(self, session: ChatSession, first_message: str) -> None:
        """Name an untitled thread after its first user message.

        Deliberately not an LLM call: a title is not worth a second round-trip
        and a second failure mode on every new conversation.
        """
        if session.title:
            return

        title = ' '.join(first_message.split())[:TITLE_MAX_LENGTH].strip()
        if not title:
            return

        await self.chat_session_repository.find_one_and_update(
            {'id': session.id, 'is_deleted': False}, title=title
        )
