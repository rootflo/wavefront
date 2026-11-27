from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class AppMigration(Base):
    """One row per app migration this deployment has started.

    App migrations are the one-time changes Alembic cannot make because they
    need application code (KMS, the bucket, Redis); see
    floware/app_migrations. A revision with no row has not been run here.
    """

    __tablename__ = 'app_migrations'

    revision: Mapped[str] = mapped_column(String(length=64), primary_key=True)
    description: Mapped[str] = mapped_column(String(length=255), nullable=False)
    # running | applied | failed | reverted
    status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    summary: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # cli | stamp
    applied_by: Mapped[str] = mapped_column(String(length=32), nullable=False)
    app_version: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
