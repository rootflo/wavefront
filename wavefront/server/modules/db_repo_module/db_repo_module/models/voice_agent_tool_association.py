import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class VoiceAgentToolAssociation(Base):
    __tablename__ = 'voice_agent_tool_associations'

    __table_args__ = (
        UniqueConstraint('voice_agent_id', 'tool_id', name='uq_voice_agent_tool'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    voice_agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('voice_agents.id'), nullable=False, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('voice_agent_tools.id'), nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    config_overrides: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (VoiceAgentToolAssociation()).__tablename__

    def to_dict(self):
        """Convert model to dictionary"""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)

            # Handle UUID serialization
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            # Handle datetime serialization
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            # Handle JSONB fields
            elif column.name == 'config_overrides':
                result[column.name] = value if value else None
            else:
                result[column.name] = value

        return result
