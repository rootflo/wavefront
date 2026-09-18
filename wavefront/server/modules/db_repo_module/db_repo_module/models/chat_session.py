import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, desc, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class ChatSession(Base):
    """One user's conversation thread with one chatbot.

    Named `chat_sessions` rather than `sessions` because `Session` /
    `user_session` is already the auth login session.

    `system_prompt_snapshot` pins the chatbot's prompt at creation time. Without
    it, editing `chatbots.system_prompt` would silently rewrite the premise of
    every past conversation, and no reply could be explained after the fact.
    """

    __tablename__ = 'chat_sessions'
    __table_args__ = (
        # Leads with user_id, so this doubles as the index for that foreign key
        # as well as serving the "my sessions, newest first" listing.
        Index(
            'ix_chat_sessions_user_id_created_at',
            'user_id',
            desc('created_at'),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    # No ondelete: chatbot deletion is soft, so sessions must outlive it.
    chatbot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('chatbots.id'), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE'), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    system_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    # Attribute is `metadata_` because `metadata` is reserved on SQLAlchemy's
    # declarative base; the column itself is still named `metadata`.
    # Nothing reads this yet -- it exists so per-session data can land later
    # without a migration.
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        'metadata', JSONB, nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    # Tracks mutations to THIS row (title, soft delete, metadata) only.
    # Deliberately NOT bumped on message insert -- session ordering uses
    # created_at. Do not treat this as "last message at".
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    @staticmethod
    def get_table_name():
        return ChatSession.__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'chatbot_id': str(self.chatbot_id),
            'user_id': str(self.user_id),
            'title': self.title,
            'system_prompt_snapshot': self.system_prompt_snapshot,
            'metadata': self.metadata_,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
