import base64
from typing import List, Optional, Tuple
import uuid

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Query
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.models.knowledge_base_schema import (
    NewInference,
)
from knowledge_base_module.services.kb_rag_retrieve import KBRagResponse
from knowledge_base_module.services.image_rag_retrieve import ImageRagRetrieve
from flo_cloud.cloud_storage import CloudStorageManager
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy import Result
from sqlalchemy import select

rag_retrieval_router = APIRouter()


class KnowledgeInferenceResponse(BaseModel):
    """Response model for knowledge base data."""

    inference_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    inference_content: dict
    created_at: datetime
    updated_at: datetime


class RetrieveSchema(BaseModel):
    """Response model for Retrieve schema."""

    embedding: Optional[List[float]] = None
    query: str
    kb_id: uuid.UUID
    threshold: Optional[float] = None
    top_k: Optional[int] = None
    vector_weight: Optional[float] = None
    keyword_weight: Optional[float] = None


class EmbeddingSchema(BaseModel):
    """Response model for Embedding vector."""

    embedding_vector: List[List[float]]
    embedding_vector_1: Optional[List[List[float]]] = Field(
        default_factory=lambda: [[]]
    )
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
    """Recursively converts UUID objects in a dictionary or list to strings."""
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


@rag_retrieval_router.post('/v1/knowledge-base/{kb_id}/retrieve')
@inject
async def retrieve_query(
    kb_id: uuid.UUID,
    query: Optional[str] = None,
    payload: Optional[ImagePayload] = None,
    threshold: Optional[float] = Query(None, description='Cosine similarity threshold'),
    top_k: Optional[int] = Query(None, description='Number of results to return'),
    vector_weight: Optional[float] = Query(
        None, description='Weight for vector similarity score'
    ),
    keyword_weight: Optional[float] = Query(
        None, description='Weight for keyword similarity score'
    ),
    offset: Optional[int] = Query(None, description='Number of results to skip'),
    limit: Optional[int] = Query(
        None, description='Number of results to return (overrides top_k)'
    ),
    query_filter: str | None = Query(None, alias='$filter'),
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
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the mentioned id doesnt exist'
            ),
        )
    if query:
        retrieved_docs = await rag_retrieval.retrieve_documents(
            query,
            kb_id,
            threshold,
            vector_weight,
            keyword_weight,
            query_filter,
            offset,
            limit,
        )
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
            threshold,
            top_k,
            query_filter,
            offset,
            limit,
        )
        retrieved_docs = convert_uuids_to_str(retrieved_docs)
    if not retrieved_docs:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data={'documents': []}),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'documents': retrieved_docs}
        ),
    )


@rag_retrieval_router.post('/v1/knowledge-base/{kb_id}/augment/{inference_id}')
@inject
async def rag_response(
    kb_id: uuid.UUID,
    inference_id: uuid.UUID,
    query: Optional[str] = Query(None, description='rag query to passed'),
    model: Optional[str] = Query(None, description='model name to be passed'),
    threshold: Optional[float] = Query(None, description='Cosine similarity threshold'),
    vector_weight: Optional[float] = Query(
        None, description='Weight for vector similarity score'
    ),
    keyword_weight: Optional[float] = Query(
        None, description='Weight for keyword similarity score'
    ),
    offset: Optional[int] = Query(None, description='Number of results to skip'),
    limit: Optional[int] = Query(
        None, description='Number of results to return (overrides top_k)'
    ),
    query_filter: str | None = Query(None, alias='$filter'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    rag_retrieval: KBRagResponse = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_retrieve]
    ),
    kb_inference_repository: SQLAlchemyRepository[KnowledgeBaseInferences] = Depends(
        Provide[KnowledgeBaseContainer.kb_inference_repository]
    ),
):
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the mentioned id doesnt exist'
            ),
        )
    existing_inference = await kb_inference_repository.find_one(
        knowledge_base_id=kb_id, inference_id=inference_id
    )
    if not existing_inference:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base inference with the mentioned knowledge_base_id and inference_id doesnt exist'
            ),
        )
    # Validate query is provided
    if not query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Query must be provided either in request body or as query parameter'
            ),
        )

    # Fetch LLM config if provided
    llm_config = None
    llm_inference_config_id = existing_inference.config_id
    async with kb_inference_repository.session() as session:
        statement = (
            select(LlmInferenceConfig)
            .join(
                KnowledgeBaseInferences,
                LlmInferenceConfig.id == KnowledgeBaseInferences.config_id,
            )
            .where(LlmInferenceConfig.id == llm_inference_config_id)
        )
        result: Result = await session.execute(statement)
        llm_config_result = result.scalars().first()
        llm_config_dict = (
            llm_config_result.to_dict(exclude_api_key=False)
            if llm_config_result
            else None
        )

    if not llm_config_dict:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'LLM inference configuration not found: {llm_inference_config_id}'
            ),
        )
    else:
        llm_config = LlmInferenceConfig(**llm_config_dict)

    prompt = existing_inference.inference_content
    response = await rag_retrieval.query(
        query,
        kb_id,
        prompt,
        threshold,
        vector_weight,
        keyword_weight,
        model,
        query_filter,
        offset,
        limit,
        llm_config,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'response': response}),
    )


@rag_retrieval_router.post(
    '/v1/knowledge-base/{kb_id}/llm_config/{config_id}/inference'
)
@inject
async def create_system_prompt(
    kb_id: uuid.UUID,
    config_id: uuid.UUID,
    inference: NewInference,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    kb_inference_repository: SQLAlchemyRepository[KnowledgeBaseInferences] = Depends(
        Provide[KnowledgeBaseContainer.kb_inference_repository]
    ),
    llm_config_repository: SQLAlchemyRepository[LlmInferenceConfig] = Depends(
        Provide[KnowledgeBaseContainer.llm_config_repository]
    ),
):
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the mentioned id doesnt exist'
            ),
        )
    llm_config = await llm_config_repository.find_one(id=config_id)
    if not llm_config:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'LLM config id is not present on llm config table'
            ),
        )
    async with kb_inference_repository.session() as session:
        new_inference = KnowledgeBaseInferences(
            knowledge_base_id=kb_id,
            inference_content=inference.prompt,
            config_id=config_id,
        )
        session.add(new_inference)
        await session.flush()
        new_inference_id = new_inference.inference_id
        await session.commit()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Created the knowledge base inference table successfully',
                    'inference_id': str(new_inference_id),
                }
            ),
        )


@rag_retrieval_router.get('/v1/knowledge-base/{kb_id}/inference')
@inject
async def get_system_prompt(
    kb_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    kb_inference_repository: SQLAlchemyRepository[KnowledgeBaseInferences] = Depends(
        Provide[KnowledgeBaseContainer.kb_inference_repository]
    ),
):
    existing_inference = await kb_inference_repository.find_one(knowledge_base_id=kb_id)
    if not existing_inference:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data={'resources': []}),
        )

    async with kb_inference_repository.session() as session:
        query = select(KnowledgeBaseInferences).where(
            KnowledgeBaseInferences.knowledge_base_id == kb_id
        )

        results: Result = await session.execute(query)
        resources = results.scalars().all()
        data = [res.to_dict() for res in resources]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data={'resources': data}),
        )


@rag_retrieval_router.delete('/v1/knowledge-base/{kb_id}/inference/{inference_id}')
@inject
async def delete_system_prompt(
    kb_id: uuid.UUID,
    inference_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    kb_inference_repository: SQLAlchemyRepository[KnowledgeBaseInferences] = Depends(
        Provide[KnowledgeBaseContainer.kb_inference_repository]
    ),
):
    existing_inference = await kb_inference_repository.find_one(
        knowledge_base_id=kb_id, inference_id=inference_id
    )
    if not existing_inference:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Inference Id is not present in the knowledge base inference'
            ),
        )

    # Delete document and embeddings
    await kb_inference_repository.delete_all(
        inference_id=inference_id, knowledge_base_id=kb_id
    )

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Deleted the inference  successfully',
                'inference_id': str(inference_id),
            }
        ),
    )


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
    knowledge_base_embeddings_repository: SQLAlchemyRepository[
        KnowledgeBaseEmbeddings
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_embeddings_repository]),
) -> JSONResponse:
    embeddings_table = []
    for embedding in payload.embeddings:
        existing_kb = await knowledge_base_repository.find_one(id=embedding.kb_id)
        if not existing_kb:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'There is no knowledge bases based on the id'
                ),
            )
        vector_size = existing_kb.vector_size
        vector_size_1 = existing_kb.vector_size_1
        if len(embedding.embedding_vector[0]) != vector_size or (
            vector_size_1 and len(embedding.embedding_vector_1[0]) != vector_size_1
        ):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    "The vector size on the embedding doesn't match the required embedding vector size"
                ),
            )

        kb_embeddings = [
            KnowledgeBaseEmbeddings(
                document_id=embedding.document_id,
                embedding_vector=embedding.embedding_vector[index],
                embedding_vector_1=embedding.embedding_vector_1[index]
                if embedding.embedding_vector_1[index]
                else None,
                chunk_text=embedding.chunk_text[index],
                chunk_index=int(embedding.chunk_index[index].split('_')[1]),
            )
            for index in range(len(embedding.embedding_vector))
        ]

        embeddings_table.extend(kb_embeddings)

    async with knowledge_base_embeddings_repository.session() as session:
        session.add_all(embeddings_table)
        await session.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Created the knowledge base documents and embeddings successfully',
            }
        ),
    )


@rag_retrieval_router.post('/v1/retrieve')
@inject
async def retrieve_record(
    payload: RetrieveSchema,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    rag_retrieval: KBRagResponse = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_retrieve]
    ),
):
    existing_kb = await knowledge_base_repository.find_one(id=payload.kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                "Knowledge Base with the mentioned id doesn't exist"
            ),
        )
    if not payload.embedding:
        retrieved_docs = await rag_retrieval.retrieve_documents(
            payload.query,
            payload.kb_id,
            payload.threshold,
            payload.top_k,
            payload.vector_weight,
            payload.keyword_weight,
        )
    else:
        params = {
            'threshold': payload.threshold or 0.2,
            'top_k': payload.top_k or 5,
            'vector_weight': payload.vector_weight or 0.7,
            'keyword_weight': payload.keyword_weight or 0.3,
            'kb_id': payload.kb_id,
        }
        retrieved_docs = await rag_retrieval.combined_search_with_reranking(
            payload.query, payload.embedding, params
        )
        for doc in retrieved_docs:
            for key, value in doc.items():
                if isinstance(value, uuid.UUID):
                    doc[key] = str(value)
    if not retrieved_docs:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'There doesnt exist any matching documents on the mentioned query {payload.query}'
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'documents': retrieved_docs}
        ),
    )
