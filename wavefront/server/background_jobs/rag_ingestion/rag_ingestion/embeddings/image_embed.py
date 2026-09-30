import base64
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import httpx
from flo_utils.utils.log import logger

from rag_ingestion.env import IMAGE_EMBEDDING_BATCH_SIZE, INFERENCE_SERVICE_URL
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject

# Status codes that mean "try again shortly" rather than "this request is bad".
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

# Upper bound on how long a Retry-After header can make us wait.
_MAX_RETRY_AFTER_SECONDS = 60.0


@dataclass
class ImageEmbeddingResult:
    """Outcome for one image: exactly one of embedding / error is set."""

    embedding: Optional[KnowledgeBaseEmbeddingObject] = None
    error: Optional[Exception] = None


class ImageEmbedding:
    """Image embeddings via the inference service (CLIP + DINO)."""

    def __init__(
        self,
        batch_size: int = IMAGE_EMBEDDING_BATCH_SIZE,
        max_retries: int = 3,
        initial_delay: float = 1.0,
    ):
        if not INFERENCE_SERVICE_URL:
            raise ValueError(
                'INFERENCE_SERVICE_URL must be set for image embedding API calls'
            )
        base = INFERENCE_SERVICE_URL.rstrip('/')
        self._embed_url = f'{base}/inference/v1/query/embeddings'
        self._embed_batch_url = f'{base}/inference/v1/query/embeddings/batch'
        self.batch_size = max(1, batch_size)
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        # Inference runs on CPU and serialises requests, so a batch can wait
        # behind others before it even starts; allow for that in the read timeout.
        self._client = httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0))
        logger.info(
            f'Image embedding endpoint: {self._embed_batch_url} '
            f'(batch size {self.batch_size})'
        )

    def embed_image(self, file_content: bytes) -> KnowledgeBaseEmbeddingObject:
        body = self._post_with_retry(
            self._embed_url, {'image_data': self._encode(file_content)}
        )
        clip, dino = self._parse_response(body, expected_count=None)
        return self._to_embedding(clip, dino)

    def embed_images(self, contents: List[bytes]) -> List[ImageEmbeddingResult]:
        """Embed images in batches of at most `batch_size`.

        Returns one result per input, in order. A failure affects only the
        images it applies to: if the service rejects a batch as invalid (e.g.
        one image cannot be decoded), that batch is retried one image at a
        time so only the bad image fails.
        """
        results: List[ImageEmbeddingResult] = []
        for start in range(0, len(contents), self.batch_size):
            results.extend(self._embed_chunk(contents[start : start + self.batch_size]))
        return results

    def _embed_chunk(self, chunk: List[bytes]) -> List[ImageEmbeddingResult]:
        try:
            body = self._post_with_retry(
                self._embed_batch_url,
                {'image_batch': [self._encode(content) for content in chunk]},
            )
            clips, dinos = self._parse_response(body, expected_count=len(chunk))
        except httpx.HTTPStatusError as err:
            if not err.response.is_client_error:
                return [ImageEmbeddingResult(error=err) for _ in chunk]
            # 400 (bad image in the batch) or 413 (batch larger than the
            # service allows): isolate the failure by embedding one at a time.
            logger.warning(
                f'Batch of {len(chunk)} images rejected with '
                f'{err.response.status_code}: {err.response.text}; '
                'retrying one image at a time'
            )
            return [self._embed_one(content) for content in chunk]
        except Exception as err:
            return [ImageEmbeddingResult(error=err) for _ in chunk]
        return [
            ImageEmbeddingResult(embedding=self._to_embedding(clip, dino))
            for clip, dino in zip(clips, dinos)
        ]

    def _embed_one(self, content: bytes) -> ImageEmbeddingResult:
        try:
            return ImageEmbeddingResult(embedding=self.embed_image(content))
        except Exception as err:
            return ImageEmbeddingResult(error=err)

    def _post_with_retry(self, url: str, payload: dict) -> Any:
        """POST, retrying connection failures and 429/502/503/504 with backoff.

        A 429's Retry-After header, when present, sets the minimum wait before
        the next attempt. Read timeouts are not retried: the service is still
        working on the request, and re-sending it would only add to its queue.
        """
        delay = self.initial_delay
        for attempt in range(1, self.max_retries + 1):
            wait = delay
            try:
                response = self._client.post(url, json=payload)
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    return response.json()
                last_error: Exception = httpx.HTTPStatusError(
                    f'{response.status_code} from inference service',
                    request=response.request,
                    response=response,
                )
                wait = max(wait, self._retry_after_seconds(response))
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.RemoteProtocolError,
            ) as err:
                last_error = err
            if attempt < self.max_retries:
                logger.warning(
                    f'Inference call to {url} failed (attempt {attempt}/'
                    f'{self.max_retries}): {last_error}; retrying in {wait:.1f}s'
                )
                time.sleep(wait)
                delay *= 1.5
        raise last_error

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float:
        """Seconds from a Retry-After header (capped), or 0 if absent/invalid."""
        try:
            seconds = float(response.headers.get('Retry-After', 0))
        except ValueError:
            return 0.0
        return min(max(seconds, 0.0), _MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _encode(content: bytes) -> str:
        return base64.b64encode(content).decode('ascii')

    @staticmethod
    def _parse_response(body: Any, expected_count: Optional[int]):
        """Pull the CLIP and DINO vectors out of a (batch) embedding response.

        Returns (clip, dino): single vectors when expected_count is None, else
        lists of expected_count vectors.
        """
        embeddings = (
            body.get('data', {}).get('response') if isinstance(body, dict) else None
        )
        if not isinstance(embeddings, list) or len(embeddings) < 2:
            raise ValueError(
                f'Unexpected embedding response shape — expected list of at least 2 entries: {body!r}'
            )

        clip_entry, dino_entry = embeddings[0], embeddings[1]
        if not isinstance(clip_entry, dict) or 'clip' not in clip_entry:
            raise ValueError(
                f'Missing CLIP embedding in response entry: {clip_entry!r}'
            )
        if not isinstance(dino_entry, dict) or 'dino' not in dino_entry:
            raise ValueError(
                f'Missing DINO embedding in response entry: {dino_entry!r}'
            )

        clip, dino = clip_entry['clip'], dino_entry['dino']
        if expected_count is not None and (
            len(clip) != expected_count or len(dino) != expected_count
        ):
            raise ValueError(
                f'Expected {expected_count} embeddings per model, got '
                f'{len(clip)} CLIP and {len(dino)} DINO'
            )
        return clip, dino

    @staticmethod
    def _to_embedding(
        clip: List[float], dino: List[float]
    ) -> KnowledgeBaseEmbeddingObject:
        return KnowledgeBaseEmbeddingObject(
            embedding_vector=clip,
            embedding_vector_1=dino,
            chunk_text='image data',
            chunk_index='chunk_0',
        )
