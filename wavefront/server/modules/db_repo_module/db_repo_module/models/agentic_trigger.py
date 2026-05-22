import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class AgenticTrigger(Base):
    __tablename__ = 'agentic_triggers'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        comment='possible values: gmail',
    )
    entity_type: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        comment='possible values: agent, workflow',
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(length=255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        server_default='pending_auth',
        comment='possible values: pending_auth, active, paused, error, deleted',
    )
    filter_config: Mapped[dict] = mapped_column(JSONB, nullable=True)
    provider_config: Mapped[dict] = mapped_column(JSONB, nullable=True)
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agentic_trigger_credentials.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'provider': self.provider,
            'entity_type': self.entity_type,
            'entity_id': str(self.entity_id),
            'namespace': self.namespace,
            'status': self.status,
            'filter_config': self.filter_config,
            'provider_config': self.provider_config,
            'credential_id': str(self.credential_id) if self.credential_id else None,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
