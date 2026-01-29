import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
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

    # TTS/STT configuration
    tts_voice_ids: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tts_parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    stt_parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Multi-language and phone number support
    inbound_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outbound_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    supported_languages: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=lambda: ['en']
    )
    default_language: Mapped[str] = mapped_column(
        String(length=10), nullable=False, default='en'
    )

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
            elif column.name in [
                'conversation_config',
                'inbound_numbers',
                'outbound_numbers',
                'supported_languages',
                'tts_parameters',
                'stt_parameters',
                'tts_voice_ids',
            ]:
                # Parse JSON/JSONB fields
                if value:
                    try:
                        # JSONB fields are already deserialized by SQLAlchemy
                        if isinstance(value, str):
                            result[column.name] = json.loads(value)
                        else:
                            result[column.name] = value
                    except (json.JSONDecodeError, TypeError):
                        result[column.name] = value
                else:
                    # Return empty list for JSONB array fields, None for others
                    result[column.name] = (
                        []
                        if column.name
                        in [
                            'inbound_numbers',
                            'outbound_numbers',
                            'supported_languages',
                        ]
                        else None
                    )
            else:
                result[column.name] = value
        return result
