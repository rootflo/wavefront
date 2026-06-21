import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class AgenticTriggerEvent(Base):
    __tablename__ = 'agentic_trigger_events'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    trigger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agentic_triggers.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    provider_event_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        comment='possible values: received, filtered_out, dispatched, failed',
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(length=1024), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    processed_at: Mapped[datetime] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint(
            'trigger_id', 'provider_event_id', name='uq_trigger_event_provider_id'
        ),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'trigger_id': str(self.trigger_id),
            'provider_event_id': self.provider_event_id,
            'status': self.status,
            'execution_id': str(self.execution_id) if self.execution_id else None,
            'subject': self.subject,
            'error': self.error,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'processed_at': self.processed_at.isoformat()
            if self.processed_at
            else None,
        }
