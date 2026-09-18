import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class Chatbot(Base):
    """A configured text chatbot: a system prompt bound to an LLM config.

    Distinct from `agents`, whose prompts live in versioned YAML in cloud storage
    and which exist to be orchestrated into workflows. A chatbot is the simpler
    product surface -- one prompt, one model, a persistent thread per user.

    Deleting is soft (`is_deleted`), so `chat_sessions` pointing here stay
    readable after a chatbot is retired.
    """

    __tablename__ = 'chatbots'
    __table_args__ = (
        # Partial, not a plain UniqueConstraint: deletes here are soft, so a
        # global constraint would let a deleted row keep reserving its name
        # forever. Deleting `support-bot` and creating it again is a routine
        # admin action, and it would fail against a chatbot no longer visible
        # anywhere. `agents` gets away with a table-level constraint because it
        # hard-deletes.
        Index(
            'uq_chatbots_namespace_name_active',
            'namespace',
            'name',
            unique=True,
            postgresql_where=text('is_deleted = false'),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    namespace: Mapped[str] = mapped_column(
        ForeignKey('namespaces.name'), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('llm_inference_config.id'), nullable=False, index=True
    )
    # Per-chatbot overrides on top of the llm_inference_config row. Only
    # `temperature` is honoured today.
    #
    # Resolve every key by PRESENCE, never truthiness -- `{"temperature": 0}` is a
    # legitimate setting and is falsy, so `config.get('temperature') or fallback`
    # would silently discard it.
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # New chatbots start disabled so a half-written system prompt can't be
    # chatted with before its author is ready.
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    @staticmethod
    def get_table_name():
        return Chatbot.__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'namespace': self.namespace,
            'name': self.name,
            'description': self.description,
            'system_prompt': self.system_prompt,
            'welcome_message': self.welcome_message,
            'llm_config_id': str(self.llm_config_id),
            'config': self.config,
            'enabled': self.enabled,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
