import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..database.base import Base


class Authenticator(Base):
    __tablename__ = 'authenticator'

    auth_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auth_name: Mapped[str] = mapped_column(
        String(length=64), nullable=False, unique=True
    )
    auth_type: Mapped[str] = mapped_column(String, nullable=False)
    auth_desc: Mapped[str] = mapped_column(String, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("auth_name !~ '\\s'", name='auth_name_no_spaces'),
    )

    @staticmethod
    def get_table_name():
        return (Authenticator()).__tablename__
