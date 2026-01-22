import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class SttConfig(Base):
    __tablename__ = 'stt_configs'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    display_name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(
        String(length=500), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    api_key: Mapped[str] = mapped_column(String(length=512), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (SttConfig()).__tablename__

    def to_dict(self, exclude_api_key: bool = True):
        result = {}
        for column in self.__table__.columns:
            # Skip api_key in responses for security
            if exclude_api_key and column.name == 'api_key':
                continue

            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result
