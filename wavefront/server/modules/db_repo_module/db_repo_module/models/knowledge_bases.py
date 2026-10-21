from datetime import datetime
from enum import Enum
import json
from typing import Dict, Optional, Tuple
import uuid

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base
from .knowledge_base_embeddings import TEXT_EMBEDDING_DIM

# Image knowledge bases embed with CLIP (vector_size) and DINOv3 (vector_size_1)
IMAGE_CLIP_DIM = 512
IMAGE_DINO_DIM = 1024


class KnowledgeBaseType(str, Enum):
    """What a knowledge base holds, which decides its embedding models and
    the files it accepts."""

    TEXT = 'text'  # BGE-M3 dense + sparse; text and PDF files
    IMAGE = 'image'  # CLIP + DINOv3; image files


# (vector_size, vector_size_1) each type's models produce
KB_VECTOR_SIZES: Dict[KnowledgeBaseType, Tuple[int, Optional[int]]] = {
    KnowledgeBaseType.TEXT: (TEXT_EMBEDDING_DIM, None),
    KnowledgeBaseType.IMAGE: (IMAGE_CLIP_DIM, IMAGE_DINO_DIM),
}


class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'
    __table_args__ = (
        CheckConstraint("type IN ('text', 'image')", name='ck_knowledge_bases_type'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    description: Mapped[str] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(nullable=False)
    vector_size: Mapped[int] = mapped_column(nullable=True)
    vector_size_1: Mapped[int] = mapped_column(nullable=True)
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
