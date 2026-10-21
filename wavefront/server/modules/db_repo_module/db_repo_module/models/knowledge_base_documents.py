from datetime import datetime
from enum import Enum
import json
import uuid
from typing import Optional

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import ForeignKey, JSON, Text

from ..database.base import Base


class IndexStatus(str, Enum):
    """Where a document is in RAG indexing.

    QUEUED is set by floware when the document is put on the RAG queue; the
    rag_ingestion worker reports the rest through KB_INDEX_STATUS_STREAM.
    """

    QUEUED = 'QUEUED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETE = 'COMPLETE'
    FAILED = 'FAILED'


# Redis Stream the rag_ingestion worker appends index status events to and
# floware consumes (key is prefixed with floware's CacheManager namespace).
KB_INDEX_STATUS_STREAM = 'kb_document:index_status'


class KnowledgeBaseDocuments(Base):
    __tablename__ = 'knowledge_base_documents'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('knowledge_bases.id', ondelete='CASCADE'),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(nullable=False)
    file_name: Mapped[str] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now)
    metadata_value: Mapped[dict] = mapped_column(
        JSON, nullable=True, default=lambda: {}
    )
    # Real, indexed columns (in addition to the equivalent keys already
    # carried inside `metadata_value`) so date-window filtering (e.g. the
    # repeat-pledge exact-match check) can use a real btree index instead of
    # unindexed JSON text extraction.
    #
    # Deliberately generic -- wavefront is a shared KB/RAG service used by
    # multiple callers, so it has no business knowing about domain concepts
    # like "loan" or "branch". Callers own the mapping of their own fields
    # onto these generic slots (e.g. flo-api currently maps
    # branch->filter1, zone->filter2, item_type->filter3, loan_id->filter4);
    # filter5/filter6 are headroom for future filter needs. Every slot has
    # a (knowledge_base_id, filterN, document_date) composite index (see the
    # migration), so any caller can filter on knowledge_base_id + any one
    # filter slot via a real btree index regardless of which slot it uses.
    document_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    filter1: Mapped[Optional[str]] = mapped_column(nullable=True)
    filter2: Mapped[Optional[str]] = mapped_column(nullable=True)
    filter3: Mapped[Optional[str]] = mapped_column(nullable=True)
    filter4: Mapped[Optional[str]] = mapped_column(nullable=True)
    filter5: Mapped[Optional[str]] = mapped_column(nullable=True)
    filter6: Mapped[Optional[str]] = mapped_column(nullable=True)
    # RAG indexing state (see IndexStatus). NULL for documents uploaded before
    # status tracking existed.
    index_status: Mapped[Optional[str]] = mapped_column(nullable=True)
    index_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Worker-side (UTC) time of the status event last applied. Events can arrive
    # out of order, so an update only applies if it is newer than this.
    index_status_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

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
