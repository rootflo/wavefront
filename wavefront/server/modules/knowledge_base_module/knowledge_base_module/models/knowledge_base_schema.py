from typing import FrozenSet, Optional

from common_module.utils.image_formats import SUPPORTED_PILLOW_MIME_TYPES
from db_repo_module.models.knowledge_bases import KB_VECTOR_SIZES, KnowledgeBaseType
from pydantic import BaseModel, model_validator


class NewKnowledge(BaseModel):
    name: str
    description: str
    type: KnowledgeBaseType
    # Derived from `type` (the sizes its embedding models produce). Optional;
    # if sent, they must match, so old clients that send them keep working.
    vector_size: Optional[int] = None
    vector_size_1: Optional[int] = None

    @model_validator(mode='after')
    def _vector_sizes_match_type(self) -> 'NewKnowledge':
        expected_size, expected_size_1 = KB_VECTOR_SIZES[self.type]
        if self.vector_size is not None and self.vector_size != expected_size:
            raise ValueError(
                f'{self.type.value} knowledge bases use vector_size '
                f'{expected_size}; omit vector_size to have it set automatically'
            )
        # Older clients sent 0 for "no second vector"
        sent_size_1 = self.vector_size_1 or None
        if self.vector_size_1 is not None and sent_size_1 != expected_size_1:
            uses = (
                f'use vector_size_1 {expected_size_1}'
                if expected_size_1
                else 'have no vector_size_1'
            )
            raise ValueError(
                f'{self.type.value} knowledge bases {uses}; omit vector_size_1 '
                'to have it set automatically'
            )
        return self


class UpdateKnowledge(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    # Accepted only if unchanged: the type decides the embedding models, so
    # existing embeddings would no longer fit a different type.
    type: Optional[KnowledgeBaseType] = None


# Upload content types each knowledge base type accepts: what rag_ingestion's
# FileProcessor can turn into that type's embeddings.
ACCEPTED_UPLOAD_TYPES: dict[KnowledgeBaseType, FrozenSet[str]] = {
    KnowledgeBaseType.TEXT: frozenset(
        {'text/plain', 'application/pdf', 'application/x-pdf'}
    ),
    KnowledgeBaseType.IMAGE: SUPPORTED_PILLOW_MIME_TYPES,
}


def upload_rejection_reason(kb_type: str, content_type: Optional[str]) -> Optional[str]:
    """Why a file of `content_type` can't go into a `kb_type` knowledge base,
    or None if it can."""
    try:
        accepted = ACCEPTED_UPLOAD_TYPES[KnowledgeBaseType(kb_type)]
    except ValueError:
        return f'Knowledge base has an unsupported type {kb_type!r}'
    mime_type = (content_type or '').split(';')[0].strip().lower()
    if mime_type in accepted:
        return None
    return (
        f'{kb_type} knowledge bases accept {", ".join(sorted(accepted))}; '
        f'got {content_type or "no content type"}'
    )
