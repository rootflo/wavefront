from datetime import datetime
import os
import uuid

from pgvector import SparseVector
from pgvector.sqlalchemy import SPARSEVEC, Vector
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base

# BGE-M3 (the only text embedding model): dense vectors are 1024-dim, and sparse
# (lexical) vectors are indexed by token id over its 250,002-token vocabulary.
TEXT_EMBEDDING_DIM = 1024
TEXT_SPARSE_EMBEDDING_DIM = 250002


class _SparseVectorAsText(TypeDecorator):
    """Test-only stand-in for SPARSEVEC on databases without pgvector: stores
    a SparseVector in pgvector's text form, as SPARSEVEC would send it."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.to_text() if isinstance(value, SparseVector) else value


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
    # Text knowledge bases (BGE-M3). Kept apart from the image columns above so
    # each modality has its own column and HNSW graph; text rows leave
    # embedding_vector / embedding_vector_1 NULL, image rows leave these NULL.
    text_embedding = (
        Column(Vector(TEXT_EMBEDDING_DIM), nullable=True)
        if os.environ.get('APP_ENV') != 'test'
        else Column(Text)
    )
    text_sparse_embedding = (
        Column(SPARSEVEC(TEXT_SPARSE_EMBEDDING_DIM), nullable=True)
        if os.environ.get('APP_ENV') != 'test'
        else Column(_SparseVectorAsText)
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    token = Column(TSVECTOR)
