from typing import Any, Dict, List

import httpx
from flo_utils.utils.log import logger

from rag_ingestion.embeddings.inference_http import post_with_retry
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject


TEXT_EMBEDDINGS_PATH = '/inference/v1/query/text-embeddings'


class EmbeddingFunc:
    """Chunk embeddings from the inference app's BGE-M3 text endpoint.

    floware embeds search queries with the same endpoint and model, so query
    and chunk vectors are comparable.
    """

    def __init__(
        self,
        inference_service_url: str,
        max_batch_size: int | str = 16,
        max_retries: int = 3,
        initial_delay: float = 1.0,
    ):
        # Matches the inference app's MAX_TEXT_EMBEDDING_BATCH_SIZE default
        self.max_batch_size = int(max_batch_size)
        base = (inference_service_url or '').rstrip('/')
        self.url = f'{base}{TEXT_EMBEDDINGS_PATH}'
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        # One connection pool for every batch. Inference runs on CPU and
        # serialises requests, so a batch can queue behind others first.
        self._client = httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0))
        logger.info(f'Text embedding endpoint: {self.url}')

    def generate_document_embeddings(self, chunks):
        contents = [v['content'] for v in chunks.values()]
        # One request per batch of up to max_batch_size chunks, covering every
        # batch, so a document of any length gets one embedding per chunk.
        results: List[Dict[str, Any]] = []
        for start in range(0, len(contents), self.max_batch_size):
            results.extend(
                self.embed_batch(contents[start : start + self.max_batch_size])
            )
        if len(results) != len(contents):
            raise ValueError(f'Expected {len(contents)} embeddings, got {len(results)}')
        data_list = []
        for result, (k, v) in zip(results, chunks.items()):
            data_list.append(
                KnowledgeBaseEmbeddingObject(
                    chunk_text=v['content'],
                    chunk_index=k,
                    text_embedding=result['dense'],
                    text_sparse_embedding=result['sparse'],
                )
            )
        return data_list, [result['dense'] for result in results]

    def embed_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """BGE-M3 dense and sparse embeddings for a list of texts in one
        request; one {'dense', 'sparse'} result per text, in order."""
        # Retries 429 (rate limit), 503 (model still loading) and other
        # transient failures; see post_with_retry.
        body = post_with_retry(
            self._client,
            self.url,
            {'texts': texts, 'return_dense': True, 'return_sparse': True},
            self.max_retries,
            self.initial_delay,
        )
        results = (body.get('data') or {}).get('response')
        if not isinstance(results, list) or len(results) != len(texts):
            raise ValueError(
                f'Expected {len(texts)} embeddings from the inference service, '
                f'got {len(results) if isinstance(results, list) else results!r}'
            )
        for result in results:
            if 'dense' not in result or 'sparse' not in result:
                raise ValueError(
                    f'Embedding result missing dense or sparse: {result!r}'
                )
        return results
