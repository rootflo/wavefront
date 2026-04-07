import base64

import httpx
from flo_utils.utils.log import logger

from rag_ingestion.env import INFERENCE_SERVICE_URL
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject


class ImageEmbedding:
    """Image embeddings via the inference service (CLIP + DINO)."""

    def __init__(self):
        if not INFERENCE_SERVICE_URL:
            raise ValueError(
                'INFERENCE_SERVICE_URL must be set for image embedding API calls'
            )
        base = INFERENCE_SERVICE_URL.rstrip('/')
        self._embed_url = f'{base}/inference/v1/query/embeddings'
        logger.info(f'Image embedding endpoint: {self._embed_url}')

    def embed_image(self, file_content: bytes) -> KnowledgeBaseEmbeddingObject:
        payload = {'image_data': base64.b64encode(file_content).decode('ascii')}
        response = httpx.post(
            self._embed_url,
            json=payload,
            timeout=httpx.Timeout(120.0, connect=30.0),
        )
        response.raise_for_status()
        body = response.json()
        embeddings = body.get('data', {}).get('response')
        if not isinstance(embeddings, list) or len(embeddings) < 2:
            raise ValueError(
                f"Unexpected embedding response shape — expected list of at least 2 entries: {body!r}"
            )

        clip_entry, dino_entry = embeddings[0], embeddings[1]
        if not isinstance(clip_entry, dict) or 'clip' not in clip_entry:
            raise ValueError(f"Missing CLIP embedding in response entry: {clip_entry!r}")
        if not isinstance(dino_entry, dict) or 'dino' not in dino_entry:
            raise ValueError(f"Missing DINO embedding in response entry: {dino_entry!r}")

        return KnowledgeBaseEmbeddingObject(
            embedding_vector=clip_entry['clip'],
            embedding_vector_1=dino_entry['dino'],
            chunk_text='image data',
            chunk_index='chunk_0',
        )
