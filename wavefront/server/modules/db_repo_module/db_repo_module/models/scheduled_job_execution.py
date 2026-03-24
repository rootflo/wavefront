import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class ScheduledJobExecution(Base):
    __tablename__ = 'scheduled_job_execution'
    __table_args__ = (
        UniqueConstraint(
            'scheduled_job_id',
            'scheduled_for',
            name='uq_scheduled_job_execution_job_time',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, index=True
    )
    scheduled_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey('scheduled_job.id', ondelete='CASCADE'), nullable=False
    )
    execution_key: Mapped[str] = mapped_column(String(length=128), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default='running', server_default='running'
    )
    error: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
