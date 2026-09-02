from datetime import datetime
import os
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class KnowledgeBaseEmbeddings(Base):
    __tablename__ = 'knowledge_base_embeddings'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('knowledge_base_documents.id', ondelete='CASCADE'),
        nullable=False,
    )
    # Using pgvector's Vector type for proper vector storage
    embedding_vector = (
        Column(Vector) if os.environ.get('APP_ENV') != 'test' else Column(Text)
    )
    embedding_vector_1 = (
        Column(Vector, nullable=True)
        if os.environ.get('APP_ENV') != 'test'
        else Column(Text)
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    token = Column(TSVECTOR)
