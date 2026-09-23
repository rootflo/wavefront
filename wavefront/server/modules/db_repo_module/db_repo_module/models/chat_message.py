import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(Base):
    """One turn in a chat session. Immutable once written -- hence no updated_at.

    Ordering is by `created_at` alone; there is no sequence column. That is only
    sound because the send flow commits the user's message before calling the
    LLM and commits the reply afterwards, so the two rows are written in separate
    transactions. Keep it that way: batching both into one transaction would give
    them the same statement timestamp and make the order of a turn arbitrary.
    """

    __tablename__ = 'chat_messages'
    __table_args__ = (
        # Leads with session_id, so this doubles as the index for that foreign
        # key as well as serving every history read.
        Index(
            'ix_chat_messages_session_id_created_at',
            'session_id',
            'created_at',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False
    )
    role: Mapped[str] = mapped_column(String(length=32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # See ChatSession.metadata_ for why the attribute is spelled with a trailing
    # underscore. Unused in v1.
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        'metadata', JSONB, nullable=True
    )
    # Python-side default, evaluated per row at flush time. func.now() would
    # return the transaction start time, which is identical for every row in a
    # transaction -- and with no sequence column that would make ordering within
    # a turn arbitrary. No server_default, for the same reason.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    @staticmethod
    def get_table_name():
        return ChatMessage.__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'session_id': str(self.session_id),
            'role': self.role,
            'content': self.content,
            'metadata': self.metadata_,
            'created_at': self.created_at.isoformat(),
        }
