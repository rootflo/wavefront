from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class KnowledgeBaseEmbeddingObject:
    """One chunk's embeddings. Image chunks set embedding_vector (CLIP) and
    embedding_vector_1 (DINO); text chunks set text_embedding (BGE-M3 dense)
    and text_sparse_embedding (BGE-M3 sparse: {'indices', 'values'})."""

    chunk_text: str
    chunk_index: str
    embedding_vector: List[float] = field(default_factory=list)
    embedding_vector_1: Optional[List[float]] = field(default_factory=list)
    text_embedding: List[float] = field(default_factory=list)
    text_sparse_embedding: Optional[Dict[str, list]] = None
