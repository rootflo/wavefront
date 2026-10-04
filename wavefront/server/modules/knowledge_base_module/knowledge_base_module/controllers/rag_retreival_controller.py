import base64
import dataclasses
import math
from typing import List, Optional, Tuple
import uuid

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.knowledge_base_embeddings import (
    TEXT_EMBEDDING_DIM,
    TEXT_SPARSE_EMBEDDING_DIM,
    KnowledgeBaseEmbeddings,
)
from db_repo_module.models.knowledge_bases import KnowledgeBase, KnowledgeBaseType
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Query
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.embeddings.embed import TextEmbeddingError
from knowledge_base_module.services.kb_rag_retrieve import KBRagResponse
from knowledge_base_module.services.image_rag_retrieve import (
    DEFAULT_EXACT_MATCH_MAX_CANDIDATES,
    EXACT_MATCH_HARD_CEILING,
    ImageRagRetrieve,
)
from flo_cloud.cloud_storage import CloudStorageManager
from pgvector import SparseVector
from pydantic import BaseModel, Field
from datetime import datetime

rag_retrieval_router = APIRouter()


class SparseEmbeddingSchema(BaseModel):
    """A BGE-M3 sparse (lexical) vector: token ids and their weights."""

    indices: List[int]
    values: List[float]


class EmbeddingSchema(BaseModel):
    """One document's chunk embeddings.

    Image documents send embedding_vector (CLIP) and embedding_vector_1
    (DINO); text documents send text_embedding (BGE-M3 dense) and, optionally,
    text_sparse_embedding (BGE-M3 sparse), one entry per chunk.
    """

    embedding_vector: List[List[float]] = Field(default_factory=list)
    embedding_vector_1: Optional[List[List[float]]] = Field(
        default_factory=lambda: [[]]
    )
    text_embedding: List[List[float]] = Field(default_factory=list)
    text_sparse_embedding: List[SparseEmbeddingSchema] = Field(default_factory=list)
    document_id: uuid.UUID
    kb_id: uuid.UUID
    chunk_text: List[str]
    chunk_index: List[str]


class DocWiseEmbeddingSchema(BaseModel):
    """Response model for Doc wise embedding."""

    embeddings: List[EmbeddingSchema]


class ImagePayload(BaseModel):
    """Payload for Image embedding. Use image_data (base64) or image_url (gs:// or s3://); image_url has priority if both are set."""

    image_data: Optional[str] = None
    image_url: Optional[str] = None


class DocumentPayload(BaseModel):
    """Payload for Document embedding."""

    inference_id: uuid.UUID
    query: Optional[str] = None
    model: Optional[str] = None


def convert_uuids_to_str(data):
    """Recursively converts UUID objects (and dataclasses, e.g. ImageMatch)
    in a dictionary or list into JSON-safe structures."""
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        data = dataclasses.asdict(data)
    if isinstance(data, dict):
        return {key: convert_uuids_to_str(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_uuids_to_str(element) for element in data]
    elif isinstance(data, uuid.UUID):
        return str(data)
    else:
        return data


def _parse_cloud_image_url(url: str) -> Tuple[str, str, str]:
    """
    Parse gs:// or s3:// URL into (scheme, bucket, key).
    Returns (scheme, bucket, key) or raises ValueError.
    """
    url = (url or '').strip()
    if url.startswith('gs://'):
        rest = url[5:]
        if '/' not in rest:
            raise ValueError('Invalid gs:// URL: missing path after bucket')
        bucket, _, key = rest.partition('/')
        return ('gs', bucket, key)
    if url.startswith('s3://'):
        rest = url[5:]
        if '/' not in rest:
            raise ValueError('Invalid s3:// URL: missing path after bucket')
        bucket, _, key = rest.partition('/')
        return ('s3', bucket, key)
    raise ValueError('image_url must be in gs:// or s3:// format')


async def _resolve_image_data(
    payload: ImagePayload,
    cloud_storage: CloudStorageManager,
    config: dict,
    response_formatter: ResponseFormatter,
) -> Tuple[Optional[str], Optional[JSONResponse]]:
    """
    Resolve image payload to a single image_data string (base64) for the inference API.
    When both are provided, image_url has priority; otherwise uses image_data or fetches from image_url (gs:// or s3://).
    Returns (image_data, None) on success, or (None, error_json_response) on validation/fetch error.
    """
    if payload.image_url:
        pass
    elif payload.image_data:
        return (payload.image_data, None)
    else:
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Query or Image data should not be empty'
                ),
            ),
        )
    try:
        scheme, bucket, key = _parse_cloud_image_url(payload.image_url)
    except ValueError as e:
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(str(e)),
            ),
        )
    cloud_provider = (
        (config.get('cloud_config') or {}).get('cloud_provider', '').lower()
    )
    if scheme == 'gs' and cloud_provider != 'gcp':
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'image_url gs:// is only supported when cloud provider is GCP'
                ),
            ),
        )
    if scheme == 's3' and cloud_provider != 'aws':
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'image_url s3:// is only supported when cloud provider is AWS'
                ),
            ),
        )
    try:
        content = cloud_storage.read_file(bucket, key)
    except Exception as e:
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Failed to fetch image from storage: {e!s}'
                ),
            ),
        )
    image_bytes = content.read() if hasattr(content, 'read') else content
    if not image_bytes:
        return (
            None,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Image from URL is empty'
                ),
            ),
        )
    image_data_b64 = base64.b64encode(image_bytes).decode('utf-8')
    return (image_data_b64, None)


def _resolve_exact_match_candidate_cap(config: dict) -> int:
    """Resolve the exact-match candidate cap from config, clamped to `EXACT_MATCH_HARD_CEILING`."""
    knowledge_base_config = (config or {}).get('knowledge_base') or {}
    try:
        configured_cap = int(
            knowledge_base_config.get('exact_match_max_candidates')
            or DEFAULT_EXACT_MATCH_MAX_CANDIDATES
        )
    except (TypeError, ValueError):
        configured_cap = DEFAULT_EXACT_MATCH_MAX_CANDIDATES
    return min(configured_cap, EXACT_MATCH_HARD_CEILING)


def _embedding_error_response(
    err: TextEmbeddingError, response_formatter: ResponseFormatter
) -> JSONResponse:
    """503 when the inference service is up but can't embed yet (model still
    loading, disabled, or rate limited), so callers retry; 502 otherwise."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        if err.retryable
        else status.HTTP_502_BAD_GATEWAY,
        content=response_formatter.buildErrorResponse(
            f'Could not embed the query: {err}'
        ),
    )


DEFAULT_TOP_K = 10


def _result_limit(top_k: Optional[int], limit: Optional[int]) -> int:
    """How many results to return: limit if given, else top_k, else the default."""
    if limit is not None:
        return limit
    return top_k if top_k is not None else DEFAULT_TOP_K


@rag_retrieval_router.post('/v1/knowledge-base/{kb_id}/retrieve')
@inject
async def retrieve_query(
    kb_id: uuid.UUID,
    query: Optional[str] = None,
    payload: Optional[ImagePayload] = None,
    threshold: Optional[float] = Query(None, description='Cosine similarity threshold'),
    top_k: Optional[int] = Query(
        None, ge=1, description=f'Number of results to return (default {DEFAULT_TOP_K})'
    ),
    vector_weight: Optional[float] = Query(
        None, description='Weight for vector similarity score'
    ),
    keyword_weight: Optional[float] = Query(
        None, description='Weight for keyword similarity score'
    ),
    offset: Optional[int] = Query(None, description='Number of results to skip'),
    limit: Optional[int] = Query(
        None, ge=1, description='Number of results to return (overrides top_k)'
    ),
    query_filter: str | None = Query(None, alias='$filter'),
    exact_match: bool = Query(
        False,
        description=(
            'If true, run an exact (non-ANN) DINO match instead of the '
            'default top_k ANN/hybrid search. Requires image input, '
            'threshold, filter1, document_date_start, and document_date_end '
            '(filter1/document_date are optional narrowing filters on the '
            'other search modes, but required for exact_match). The '
            'underlying query never touches the HNSW index (see '
            'QueryGenerator.get_image_embedding_dino_exact_match) so results '
            'are exact, not approximate.'
        ),
    ),
    document_date_start: Optional[datetime] = Query(
        None,
        description=(
            'Start of the document_date window (inclusive), applied on '
            'knowledge_base_documents.document_date. Works with any search '
            'mode (text query, image ANN, or exact_match); must be provided '
            'together with document_date_end. Required when exact_match=true.'
        ),
    ),
    document_date_end: Optional[datetime] = Query(
        None,
        description=(
            'End of the document_date window (inclusive). Works with any '
            'search mode; must be provided together with document_date_start. '
            'Required when exact_match=true.'
        ),
    ),
    created_at_start: Optional[datetime] = Query(
        None,
        description=(
            'Start of the created_at window (inclusive), applied on '
            'knowledge_base_documents.created_at. Works with any search '
            'mode (text query, image ANN, or exact_match); must be provided '
            'together with created_at_end.'
        ),
    ),
    created_at_end: Optional[datetime] = Query(
        None,
        description=(
            'End of the created_at window (inclusive). Works with any '
            'search mode; must be provided together with created_at_start.'
        ),
    ),
    filter1: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter1. Works with '
            'any search mode (text query, image ANN, or exact_match). '
            'Required when exact_match=true.'
        ),
    ),
    filter2: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter2. Works with '
            'any search mode (text query, image ANN, or exact_match).'
        ),
    ),
    filter3: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter3. Works with '
            'any search mode (text query, image ANN, or exact_match).'
        ),
    ),
    filter4: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter4. Works with '
            'any search mode (text query, image ANN, or exact_match).'
        ),
    ),
    filter5: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter5. Works with '
            'any search mode (text query, image ANN, or exact_match).'
        ),
    ),
    filter6: Optional[str] = Query(
        None,
        description=(
            'Equality filter on knowledge_base_documents.filter6. Works with '
            'any search mode (text query, image ANN, or exact_match).'
        ),
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    rag_retrieval: KBRagResponse = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_retrieve]
    ),
    image_rag_retrieval: ImageRagRetrieve = Depends(
        Provide[KnowledgeBaseContainer.image_knowledge_base_retrieve]
    ),
    config: dict = Depends(Provide[KnowledgeBaseContainer.config]),
    cloud_storage: CloudStorageManager = Depends(
        Provide[KnowledgeBaseContainer.cloud_storage]
    ),
):
    if not query and not payload:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Query or Image data should not be empty'
            ),
        )
    if exact_match and not payload:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Image data is required when exact_match=true'
            ),
        )
    has_document_date_window = (
        document_date_start is not None and document_date_end is not None
    )
    has_created_at_window = created_at_start is not None and created_at_end is not None
    if exact_match and (
        threshold is None or not (has_document_date_window or has_created_at_window)
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'threshold and either a document_date window '
                '(document_date_start + document_date_end) or a created_at '
                'window (created_at_start + created_at_end) are required '
                'when exact_match=true'
            ),
        )
    if (document_date_start is None) != (document_date_end is None):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'document_date_start and document_date_end must be provided together'
            ),
        )
    if (created_at_start is None) != (created_at_end is None):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'created_at_start and created_at_end must be provided together'
            ),
        )
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the mentioned id doesnt exist'
            ),
        )

    match_count = None
    # One result count for every search mode: limit overrides top_k, and both
    # fall back to DEFAULT_TOP_K. (Text search used to read only limit and
    # image search only top_k; image search also crashed on a missing top_k.)
    result_limit = _result_limit(top_k, limit)

    if exact_match:
        image_data, error_response = await _resolve_image_data(
            payload, cloud_storage, config, response_formatter
        )
        if error_response is not None:
            return error_response
        inference_url = config['model']['inference_service_url']
        exact_match_max_candidates = _resolve_exact_match_candidate_cap(config)
        retrieved_docs = await image_rag_retrieval.exact_match_dino(
            image_data,
            inference_url,
            kb_id,
            filter1,
            document_date_start,
            document_date_end,
            threshold,
            filter2,
            filter3,
            filter4,
            filter5,
            filter6,
            created_at_start,
            created_at_end,
            max_candidates=exact_match_max_candidates,
        )
        retrieved_docs = convert_uuids_to_str(retrieved_docs)
        match_count = len(retrieved_docs)
    elif query:
        try:
            retrieved_docs = await rag_retrieval.retrieve_documents(
                query,
                kb_id,
                threshold,
                vector_weight,
                keyword_weight,
                query_filter,
                offset,
                result_limit,
                filter1,
                filter2,
                filter3,
                filter4,
                filter5,
                filter6,
                document_date_start,
                document_date_end,
                created_at_start,
                created_at_end,
            )
        except TextEmbeddingError as err:
            return _embedding_error_response(err, response_formatter)
    else:
        image_data, error_response = await _resolve_image_data(
            payload, cloud_storage, config, response_formatter
        )
        if error_response is not None:
            return error_response
        inference_url = config['model']['inference_service_url']
        retrieved_docs = await image_rag_retrieval.retrieve_images(
            image_data,
            inference_url,
            kb_id,
            result_limit,
            query_filter,
            filter1,
            filter2,
            filter3,
            filter4,
            filter5,
            filter6,
            document_date_start,
            document_date_end,
            created_at_start,
            created_at_end,
        )
        retrieved_docs = convert_uuids_to_str(retrieved_docs)
    if not retrieved_docs:
        empty_data = {'documents': []}
        if match_count is not None:
            empty_data['match_count'] = 0
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data=empty_data),
        )

    data = {'documents': retrieved_docs}
    if match_count is not None:
        data['match_count'] = match_count
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data=data),
    )


KB_NOT_FOUND_REASON = 'There is no knowledge bases based on the id'
VECTOR_SIZE_MISMATCH_REASON = (
    "The vector size on the embedding doesn't match the required embedding vector size"
)
# pgvector's HNSW index on sparsevec accepts at most 1,000 non-zero entries;
# BGE-M3 at 512 tokens per chunk stays well under it.
MAX_SPARSE_NONZERO = 1000


def _parse_chunk_index(value: str) -> Optional[int]:
    """'chunk_3' -> 3; None if the value is not in that form."""
    prefix, _, number = value.partition('_')
    return int(number) if prefix == 'chunk' and number.isdigit() else None


def _store_rejection_reason(
    embedding: EmbeddingSchema, kb: Optional[KnowledgeBase]
) -> Optional[str]:
    """Why this document's embeddings cannot be stored, or None if they can."""
    if kb is None:
        return KB_NOT_FOUND_REASON
    is_text = bool(embedding.text_embedding)
    is_image = bool(embedding.embedding_vector)
    if is_text and is_image:
        return 'A document must send either text or image embeddings, not both'
    if not (is_text or is_image):
        return 'The document has no embeddings'
    chunk_count = len(
        embedding.text_embedding if is_text else embedding.embedding_vector
    )
    if (
        len(embedding.chunk_text) != chunk_count
        or len(embedding.chunk_index) != chunk_count
    ):
        return 'The embeddings, chunk_text and chunk_index must have the same length'
    reason = (
        _text_rejection_reason(embedding, kb, chunk_count)
        if is_text
        else _image_rejection_reason(embedding, kb, chunk_count)
    )
    if reason:
        return reason
    if any(_parse_chunk_index(index) is None for index in embedding.chunk_index):
        return "chunk_index values must look like 'chunk_<number>'"
    return None


def _image_rejection_reason(
    embedding: EmbeddingSchema, kb: KnowledgeBase, chunk_count: int
) -> Optional[str]:
    """Image documents (CLIP + DINO vectors per chunk) only go into image
    knowledge bases."""
    if kb.type != KnowledgeBaseType.IMAGE.value:
        return (
            f'Image embeddings can only be stored in an image knowledge base; '
            f'this one is {kb.type}'
        )
    if any(len(vector) != kb.vector_size for vector in embedding.embedding_vector):
        return VECTOR_SIZE_MISMATCH_REASON
    second_vectors = embedding.embedding_vector_1 or []
    if kb.vector_size_1:
        if len(second_vectors) != chunk_count or any(
            len(vector) != kb.vector_size_1 for vector in second_vectors
        ):
            return VECTOR_SIZE_MISMATCH_REASON
    elif any(second_vectors):
        return (
            'The embedding has a second vector (e.g. an image embedding) but the '
            'knowledge base only accepts one'
        )
    return None


def _text_rejection_reason(
    embedding: EmbeddingSchema, kb: KnowledgeBase, chunk_count: int
) -> Optional[str]:
    """Text documents (BGE-M3 vectors per chunk) only go into text knowledge
    bases."""
    if kb.type != KnowledgeBaseType.TEXT.value:
        return (
            f'Text embeddings can only be stored in a text knowledge base; '
            f'this one is {kb.type}'
        )
    if any(len(vector) != TEXT_EMBEDDING_DIM for vector in embedding.text_embedding):
        return VECTOR_SIZE_MISMATCH_REASON
    sparse = embedding.text_sparse_embedding
    if sparse and len(sparse) != chunk_count:
        return 'text_sparse_embedding must have one entry per chunk'
    for vector in sparse:
        if len(vector.indices) != len(vector.values):
            return 'Sparse embedding indices and values must have the same length'
        if len(vector.indices) > MAX_SPARSE_NONZERO:
            return (
                f'Sparse embeddings may have at most {MAX_SPARSE_NONZERO} '
                'non-zero entries'
            )
        if len(set(vector.indices)) != len(vector.indices) or any(
            not 0 <= index < TEXT_SPARSE_EMBEDDING_DIM for index in vector.indices
        ):
            return (
                'Sparse embedding indices must be unique token ids in '
                f'[0, {TEXT_SPARSE_EMBEDDING_DIM})'
            )
        if not all(math.isfinite(value) for value in vector.values):
            return 'Sparse embedding values must be finite numbers'
    return None


def _sparse_value(vector: Optional[SparseEmbeddingSchema]) -> Optional[SparseVector]:
    if vector is None or not vector.indices:
        return None
    return SparseVector(
        dict(zip(vector.indices, vector.values)), TEXT_SPARSE_EMBEDDING_DIM
    )


def _embedding_rows(embedding: EmbeddingSchema) -> List[KnowledgeBaseEmbeddings]:
    is_text = bool(embedding.text_embedding)
    chunk_count = len(
        embedding.text_embedding if is_text else embedding.embedding_vector
    )
    second_vectors = embedding.embedding_vector_1 or []
    sparse = embedding.text_sparse_embedding
    rows = []
    for index in range(chunk_count):
        vectors = (
            {
                'text_embedding': embedding.text_embedding[index],
                'text_sparse_embedding': _sparse_value(
                    sparse[index] if sparse else None
                ),
            }
            if is_text
            else {
                'embedding_vector': embedding.embedding_vector[index],
                'embedding_vector_1': second_vectors[index]
                if index < len(second_vectors) and second_vectors[index]
                else None,
            }
        )
        rows.append(
            KnowledgeBaseEmbeddings(
                document_id=embedding.document_id,
                chunk_text=embedding.chunk_text[index],
                chunk_index=_parse_chunk_index(embedding.chunk_index[index]),
                # No `token` (English tsvector): text search now scores
                # keywords with BGE-M3 sparse vectors, which are multilingual.
                **vectors,
            )
        )
    return rows


@rag_retrieval_router.post('/v1/store_embedding')
@inject
async def store_embeddings(
    payload: DocWiseEmbeddingSchema,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    knowledge_base_embeddings_write_repository: SQLAlchemyRepository[
        KnowledgeBaseEmbeddings
    ] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_embeddings_write_repository]
    ),
) -> JSONResponse:
    """Store each document's embeddings, validating documents independently.

    Documents that fail validation are left out and listed under `rejected`
    in the response, so one bad document no longer fails the whole request.
    Only when every document is rejected does the request fail with 400.
    """
    embeddings_table = []
    rejected = []
    knowledge_bases: dict = {}
    for embedding in payload.embeddings:
        if embedding.kb_id not in knowledge_bases:
            knowledge_bases[embedding.kb_id] = await knowledge_base_repository.find_one(
                id=embedding.kb_id
            )
        reason = _store_rejection_reason(embedding, knowledge_bases[embedding.kb_id])
        if reason:
            rejected.append(
                {'document_id': str(embedding.document_id), 'reason': reason}
            )
            continue

        embeddings_table.extend(_embedding_rows(embedding))

    if rejected and not embeddings_table:
        reasons = list(dict.fromkeys(item['reason'] for item in rejected))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('; '.join(reasons)),
        )

    async with knowledge_base_embeddings_write_repository.session() as session:
        session.add_all(embeddings_table)
        await session.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Created the knowledge base documents and embeddings successfully',
                'rejected': rejected,
            }
        ),
    )
