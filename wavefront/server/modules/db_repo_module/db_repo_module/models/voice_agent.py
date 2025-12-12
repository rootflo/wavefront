import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class VoiceAgent(Base):
    __tablename__ = 'voice_agents'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('llm_inference_config.id'), nullable=False
    )
    tts_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('tts_configs.id'), nullable=False
    )
    stt_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('stt_configs.id'), nullable=False
    )
    telephony_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('telephony_configs.id'), nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(length=64), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (VoiceAgent()).__tablename__

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif column.name == 'conversation_config' and value:
                # Parse JSON field
                try:
                    result[column.name] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[column.name] = value
            else:
                result[column.name] = value
        return result
