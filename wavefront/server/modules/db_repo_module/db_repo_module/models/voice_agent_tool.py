import uuid
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import Enum as SQLEnum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class ToolType(str, enum.Enum):
    """Enum for tool types"""

    API = 'api'
    PYTHON = 'python'


class VoiceAgentTool(Base):
    __tablename__ = 'voice_agent_tools'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(
        String(length=100), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tool_type: Mapped[ToolType] = mapped_column(
        SQLEnum(
            ToolType,
            name='tool_type_enum',
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parameter_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (VoiceAgentTool()).__tablename__

    def to_dict(self, exclude_sensitive: bool = True):
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
            # Handle enum serialization
            elif isinstance(value, ToolType):
                result[column.name] = value.value
            # Handle JSONB fields
            elif column.name in ['config', 'parameter_schema']:
                result[column.name] = value if value else None
            else:
                result[column.name] = value

            # Optionally mask sensitive data in config
            if exclude_sensitive and column.name == 'config' and value:
                masked_config = value.copy()
                if 'auth_credentials' in masked_config:
                    masked_config['auth_credentials'] = {'masked': True}
                result[column.name] = masked_config

        return result
