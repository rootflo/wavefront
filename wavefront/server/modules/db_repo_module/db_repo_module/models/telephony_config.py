import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class TelephonyConfig(Base):
    __tablename__ = 'telephony_configs'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    display_name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(
        String(length=500), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    phone_numbers: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sip_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (TelephonyConfig()).__tablename__

    def to_dict(self, exclude_credentials: bool = True):
        result = {}
        for column in self.__table__.columns:
            # Skip credentials in responses for security
            if exclude_credentials and column.name == 'credentials':
                continue

            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif (
                column.name
                in ['credentials', 'phone_numbers', 'webhook_config', 'sip_config']
                and value
            ):
                # Parse JSON fields
                try:
                    result[column.name] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[column.name] = value
            else:
                result[column.name] = value
        return result
