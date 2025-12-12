from datetime import datetime
import uuid
import json

from sqlalchemy import ForeignKey
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class KnowledgeBaseInferences(Base):
    __tablename__ = 'knowledge_base_inferences'

    inference_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('knowledge_bases.id', ondelete='CASCADE'),
        nullable=False,
    )
    inference_content: Mapped[dict] = mapped_column(JSON, nullable=False)
    config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('llm_inference_config.id', ondelete='CASCADE'), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif column.name == 'meta':
                result[column.name] = json.loads(value) if value else None
            else:
                result[column.name] = value
        return result
