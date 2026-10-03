from typing import Any, Dict, Optional

import httpx

TEXT_EMBEDDINGS_PATH = '/inference/v1/query/text-embeddings'


class TextEmbeddingError(RuntimeError):
    """The inference service could not embed the text.

    status_code is the inference service's HTTP status, or None if it could
    not be reached.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        """The service is up but can't serve yet: model still loading or
        disabled (503), or rate limited (429)."""
        return self.status_code in (429, 503)


class EmbeddingFunc:
    """Query embeddings from the inference app's BGE-M3 text endpoint.

    The same model and endpoint embed documents at ingestion
    (rag_ingestion), so query and chunk vectors are comparable.
    """

    def __init__(self, inference_url: str):
        self.url = f'{(inference_url or "").rstrip("/")}{TEXT_EMBEDDINGS_PATH}'

    async def embed_query(self, query: str) -> Dict[str, Any]:
        """BGE-M3 dense and sparse embeddings for one query:
        {'dense': [...], 'sparse': {'indices': [...], 'values': [...]}}."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0)
            ) as client:
                response = await client.post(
                    self.url,
                    json={
                        'texts': [query],
                        'return_dense': True,
                        'return_sparse': True,
                    },
                )
        except httpx.HTTPError as err:
            raise TextEmbeddingError(
                f'Could not reach the inference service at {self.url}: {err}'
            ) from err
        if response.status_code != 200:
            raise TextEmbeddingError(
                f'Inference service returned {response.status_code}: {response.text}',
                status_code=response.status_code,
            )
        results = (response.json().get('data') or {}).get('response') or []
        if len(results) != 1 or 'dense' not in results[0] or 'sparse' not in results[0]:
            raise TextEmbeddingError(
                f'Unexpected text embedding response: {response.text[:500]}'
            )
        return {'dense': results[0]['dense'], 'sparse': results[0]['sparse']}
