import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, JSON, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class LlmInferenceConfig(Base):
    __tablename__ = 'llm_inference_config'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    llm_model: Mapped[str] = mapped_column(String(length=255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    model_type: Mapped[str] = mapped_column(
        String(length=64), nullable=False, default='llm', server_default=text("'llm'")
    )
    base_url: Mapped[Optional[str]] = mapped_column(String(length=512), nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (LlmInferenceConfig()).__tablename__

    def to_dict(self):
        """Public form for API responses: never carries the api_key."""
        return self.public_dict(self.to_stored_dict())

    def to_stored_dict(self):
        """Every column as stored, so api_key is ciphertext when encryption is on."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result

    @staticmethod
    def public_dict(stored: dict) -> dict:
        """Public form of a stored dict (e.g. one read back from the cache)."""
        result = dict(stored)
        result['has_api_key'] = bool(result.pop('api_key', None))
        return result
