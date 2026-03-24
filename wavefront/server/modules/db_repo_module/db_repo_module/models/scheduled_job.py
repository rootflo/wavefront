import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class ScheduledJob(Base):
    __tablename__ = 'scheduled_job'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, index=True
    )
    job_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(length=64), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(length=64), nullable=False, default='UTC', server_default='UTC'
    )
    status: Mapped[str] = mapped_column(
        String(length=32), nullable=False, default='active', server_default='active'
    )
    next_run_at: Mapped[datetime] = mapped_column(nullable=False)
    last_run_at: Mapped[datetime] = mapped_column(nullable=True)
    last_error: Mapped[str] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default='0'
    )
    max_retries: Mapped[int] = mapped_column(
        nullable=False, default=3, server_default='3'
    )
    locked_by: Mapped[str] = mapped_column(String(length=128), nullable=True)
    locked_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
