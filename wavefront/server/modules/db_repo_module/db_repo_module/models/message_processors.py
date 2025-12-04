from datetime import datetime
import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy import String, Text
from sqlalchemy import UUID

from sqlalchemy.orm import Mapped, mapped_column
from ..database.base import Base


class MessageProcessors(Base):
    """
    Model for storing function definitions that can be executed in isolated VMs (Node.js/Deno).
    YAML files are stored in cloud storage buckets, and the file URL is stored in the source field.
    """

    __tablename__ = 'message_processors'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(length=512), unique=True, nullable=False
    )  # YAML file URL/path in bucket
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'source': self.source,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    @staticmethod
    def get_table_name():
        return MessageProcessors.__tablename__
