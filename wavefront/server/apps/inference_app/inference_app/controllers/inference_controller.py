import base64
import binascii
import math
from typing import TYPE_CHECKING

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from inference_app.env import MAX_EMBEDDING_BATCH_SIZE, MAX_TEXT_EMBEDDING_BATCH_SIZE
from inference_app.inference_app_container import InferenceAppContainer
from inference_app.rate_limiter import SlidingWindowRateLimiter
from inference_app.service.text_embedding_provider import (
    TextEmbeddingProvider,
    TextEmbeddingUnavailable,
)

if TYPE_CHECKING:
    # Annotation only: the real model needs torch, which mock mode runs without
    from inference_app.service.image_embedding import ImageEmbedding
from pydantic import BaseModel


class ImagePayload(BaseModel):
    image_data: str  # base64 encoded image data


class ImageBatchPayload(BaseModel):
    image_batch: list[str]  # list of base64 encoded image data


class TextEmbeddingPayload(BaseModel):
    texts: list[str]
    return_dense: bool = True
    return_sparse: bool = True


@inject
async def enforce_rate_limit(
    rate_limiter: SlidingWindowRateLimiter = Depends(
        Provide[InferenceAppContainer.rate_limiter]
    ),
):
    # async so it runs on the event loop: an over-limit request is rejected
    # immediately even when every threadpool thread is waiting on the model.
    retry_after = rate_limiter.acquire()
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='Rate limit exceeded for embedding requests',
            headers={'Retry-After': str(math.ceil(retry_after))},
        )


# Health checks live on the app, not this router, so they are never limited.
inference_app_router = APIRouter(dependencies=[Depends(enforce_rate_limit)])


# The embedding handlers are plain `def` on purpose: the model forward pass is
# synchronous and slow, so FastAPI must run it in its threadpool rather than on
# the event loop, where it would stall every other request, health checks
# included.
@inference_app_router.post('/v1/query/embeddings')
@inject
def image_embedding(
    payload: ImagePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    image_embedding_service: 'ImageEmbedding' = Depends(
        Provide[InferenceAppContainer.image_embedding]
    ),
):
    try:
        image_data = extract_decoded_image_data(payload.image_data)
    except binascii.Error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Invalid base64 image data'),
        )
    try:
        embeddings = image_embedding_service.query_embed(image_data)
    except ValueError as err:
        # query_embed raises ValueError when the bytes are not a decodable image
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(err)),
        )
    if not embeddings:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No Embedding data is present'
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'response': embeddings}),
    )


@inference_app_router.post('/v1/query/embeddings/batch')
@inject
def image_embedding_batch(
    payload: ImageBatchPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    image_embedding_service: 'ImageEmbedding' = Depends(
        Provide[InferenceAppContainer.image_embedding]
    ),
):
    batch_size = len(payload.image_batch)
    if batch_size == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('image_batch is empty'),
        )
    if batch_size > MAX_EMBEDDING_BATCH_SIZE:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content=response_formatter.buildErrorResponse(
                f'Batch of {batch_size} images exceeds the maximum of '
                f'{MAX_EMBEDDING_BATCH_SIZE}'
            ),
        )
    try:
        image_batch = [
            extract_decoded_image_data(image_data) for image_data in payload.image_batch
        ]
    except binascii.Error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Invalid base64 image data in batch'
            ),
        )
    try:
        embeddings = image_embedding_service.query_embed_batch(image_batch)
    except ValueError as err:
        # query_embed_batch raises ValueError naming the image it could not decode
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(err)),
        )
    if not embeddings:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No Embedding data is present'
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'response': embeddings}),
    )


# Seconds clients are told to wait (Retry-After) while BGE-M3 is loading.
TEXT_MODEL_LOADING_RETRY_AFTER_S = 10


@inference_app_router.post('/v1/query/text-embeddings')
@inject
def text_embedding(
    payload: TextEmbeddingPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    text_embedding_provider: TextEmbeddingProvider = Depends(
        Provide[InferenceAppContainer.text_embedding_provider]
    ),
):
    """BGE-M3 dense and/or sparse embeddings, one result per text, in order.

    sparse is {indices, values}: token ids and their lexical weights, over a
    vocabulary of `sparse_dim` (e.g. for a pgvector sparsevec). Texts longer
    than MAX_TEXT_EMBEDDING_TOKENS are truncated.
    """
    batch_size = len(payload.texts)
    if batch_size == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('texts is empty'),
        )
    if batch_size > MAX_TEXT_EMBEDDING_BATCH_SIZE:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content=response_formatter.buildErrorResponse(
                f'Batch of {batch_size} texts exceeds the maximum of '
                f'{MAX_TEXT_EMBEDDING_BATCH_SIZE}'
            ),
        )
    if not (payload.return_dense or payload.return_sparse):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'At least one of return_dense or return_sparse must be true'
            ),
        )
    try:
        model = text_embedding_provider.get()
    except TextEmbeddingUnavailable as err:
        # While the model loads, tell clients when to come back; a disabled or
        # failed model won't recover by waiting, so no Retry-After then.
        loading = text_embedding_provider.status == TextEmbeddingProvider.LOADING
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_formatter.buildErrorResponse(str(err)),
            headers={'Retry-After': str(TEXT_MODEL_LOADING_RETRY_AFTER_S)}
            if loading
            else None,
        )

    embeddings = model.embed(
        payload.texts,
        return_dense=payload.return_dense,
        return_sparse=payload.return_sparse,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={
                'model': 'bge-m3',
                'dense_dim': model.dense_dim,
                'sparse_dim': model.sparse_dim,
                'response': embeddings,
            }
        ),
    )


def extract_decoded_image_data(image_data: str) -> bytes:
    """Decode base64 image data, optionally prefixed as a data URL.

    Raises binascii.Error on characters outside the base64 alphabet instead of
    silently dropping them. Whitespace (e.g. MIME line wrapping) is allowed.
    """
    parts = image_data.split(',')
    base64_data = parts[1] if len(parts) == 2 else parts[0]
    return base64.b64decode(''.join(base64_data.split()), validate=True)
