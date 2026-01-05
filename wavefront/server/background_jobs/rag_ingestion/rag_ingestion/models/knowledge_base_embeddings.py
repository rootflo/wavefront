from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class KnowledgeBaseEmbeddingObject:
    embedding_vector: List[float]
    chunk_text: str
    chunk_index: str
    embedding_vector_1: Optional[List[float]] = field(default_factory=list)


@dataclass
class RetrieveParams:
    kb_id: str
    threshold: Optional[float] = 0.2
    top_k: Optional[int] = 5
    vector_weight: Optional[float] = 0.7
    keyword_weight: Optional[float] = 0.3
