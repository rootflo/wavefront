import asyncio
from datetime import datetime
import os
import re
from typing import Optional
import uuid

from sqlalchemy import func, select

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.knowledge_base_documents import (
    IndexStatus,
    KnowledgeBaseDocuments,
)
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from fastapi import UploadFile
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from fastapi import Form
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.models.knowledge_base_schema import upload_rejection_reason
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud.cloud_storage import CloudStorageManager
from pydantic import BaseModel
from pydantic import Field
from pydantic import Json
from knowledge_base_module.queries.generate_query import QueryGenerator

kb_document_router = APIRouter()


class KnowledgeBaseDocumentResponse(BaseModel):
    """Response model for knowledge base document data."""

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    file_path: str
    file_name: str
    file_type: str
    file_size: str
    created_at: datetime
    updated_at: datetime


class DocumentMetadataRequest(BaseModel):
    """Request model for the `metadata` JSON string form field on document upload.

    `filter1`..`filter6`/`document_date` are generic -- wavefront has no notion
    of what they mean semantically, only the caller (e.g. flo-api) knows/decides
    that, say, `filter1` means "branch" for its documents. `metadata` holds any
    other caller-defined data that isn't one of those flat, indexed columns and
    is stored as-is in the `metadata_value` JSON column.
    """

    document_date: Optional[datetime] = None
    filter1: Optional[str] = Field(default=None, max_length=255)
    filter2: Optional[str] = Field(default=None, max_length=255)
    filter3: Optional[str] = Field(default=None, max_length=255)
    filter4: Optional[str] = Field(default=None, max_length=255)
    filter5: Optional[str] = Field(default=None, max_length=255)
    filter6: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[dict] = None


@kb_document_router.post('/v1/knowledge-bases/{kb_id}/documents')
@inject
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    metadata: Optional[Json[DocumentMetadataRequest]] = Form(None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    knowledge_base_documents_repository: SQLAlchemyRepository[
        KnowledgeBaseDocuments
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_documents_repository]),
    cloud_storage: CloudStorageManager = Depends(
        Provide[KnowledgeBaseContainer.cloud_storage]
    ),
    message_queue: MessageQueueManager = Depends(
        Provide[KnowledgeBaseContainer.message_queue]
    ),
    config=Depends(Provide[KnowledgeBaseContainer.config]),
) -> JSONResponse:
    """Upload and process a document for a knowledge base."""
    temp_file_path = None
    try:
        # Validate knowledge base exists
        existing_kb = await knowledge_base_repository.find_one(id=kb_id)
        if not existing_kb:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Knowledge Base with the given id does not exist'
                ),
            )

        # Only files this type of knowledge base can index, checked before
        # anything is stored or queued.
        rejection = upload_rejection_reason(existing_kb.type, file.content_type)
        if rejection:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(rejection),
            )

        # Check for existing document
        existing_kb_documents = await knowledge_base_documents_repository.find_one(
            id=kb_id
        )
        if existing_kb_documents:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Document already exists for this knowledge base'
                ),
            )

        # Process file content
        file_bytes = await file.read()
        doc_id = uuid.uuid4()
        filename = file.filename.replace(' ', '_')
        filename = re.sub(r'_{2,}', '_', filename)
        gcs_file_name = f'kb_{kb_id}/{doc_id}/{filename}'

        # Create document record
        async with knowledge_base_documents_repository.session() as session:
            new_kb_document = KnowledgeBaseDocuments(
                id=doc_id,
                knowledge_base_id=kb_id,
                file_path=gcs_file_name,
                file_name=file.filename,
                file_type=file.content_type.split('/')[1],
                file_size=file.size,
                metadata_value=metadata.metadata if metadata else None,
                document_date=metadata.document_date if metadata else None,
                filter1=metadata.filter1 if metadata else None,
                filter2=metadata.filter2 if metadata else None,
                filter3=metadata.filter3 if metadata else None,
                filter4=metadata.filter4 if metadata else None,
                filter5=metadata.filter5 if metadata else None,
                filter6=metadata.filter6 if metadata else None,
                # Set before the message is queued, not after: the worker may
                # report IN_PROGRESS before this request finishes, and that must
                # not be overwritten. Failures below flip it to FAILED.
                index_status=IndexStatus.QUEUED.value,
            )

            session.add(new_kb_document)
            await session.commit()

        # Upload to cloud storage
        logger.info(f'The data filename is {gcs_file_name}')
        bucket_name = config['storage']['application_bucket']
        try:
            await asyncio.to_thread(
                cloud_storage.save_small_file,
                file_content=file_bytes,
                bucket_name=bucket_name,
                key=gcs_file_name,
                content_type=file.content_type,
            )
        except Exception as err:
            await _mark_index_failed(
                knowledge_base_documents_repository,
                doc_id,
                f'Failed to upload the file to storage: {err}',
            )
            raise
        logger.info(f'File uploaded to cloud storage: {gcs_file_name}')
        try:
            data = {
                'bucket': bucket_name,
                'name': gcs_file_name,
                'kb_id': str(kb_id),
                'doc_id': str(doc_id),
                'file_type': file.content_type,
                'parse_type': 'kb_insertion',
            }
            message_id = message_queue.add_message(message_body=data)
            logger.info(f'The subscription message is {message_id}')

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': 'Created the knowledge base documents and embeddings successfully',
                        'knowledge_base_id': str(kb_id),
                    }
                ),
            )
        except Exception as err:
            await _mark_index_failed(
                knowledge_base_documents_repository,
                doc_id,
                f'Failed to queue the document for indexing: {err}',
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    f'Error while pushing the documents to auraflo as {err}'
                ),
            )

    except Exception as e:
        logger.error(f'Error while processing document: {str(e)}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


async def _mark_index_failed(
    knowledge_base_documents_repository: SQLAlchemyRepository[KnowledgeBaseDocuments],
    doc_id: uuid.UUID,
    error: str,
) -> None:
    """Record that a document never reached the RAG queue. Best effort: the
    request is already failing, so a second error here is only logged."""
    try:
        await knowledge_base_documents_repository.find_one_and_update(
            {'id': doc_id},
            index_status=IndexStatus.FAILED.value,
            index_error=error,
        )
    except Exception as err:
        logger.error(f'Could not mark document {doc_id} as FAILED: {err}')


def _document_row_to_dict(row: dict) -> dict:
    """Convert a raw document row to the same format as KnowledgeBaseDocuments.to_dict()."""
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


@kb_document_router.get('/v1/knowledge-bases/{kb_id}/documents')
@inject
async def get_documents(
    kb_id: uuid.UUID,
    file_type: Optional[str] = Query(None, description='Type of file to filter by'),
    query_filter: Optional[str] = Query(None, alias='$filter'),
    offset: int = Query(0, ge=0, description='The number of items to skip'),
    limit: int = Query(
        10, ge=1, le=100, description='The maximum number of items to return'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_documents_repository: SQLAlchemyRepository[
        KnowledgeBaseDocuments
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_documents_repository]),
) -> JSONResponse:
    """Get documents for a knowledge base with optional filtering and pagination."""
    try:
        query_generator = QueryGenerator()
        sql_query, query_params = query_generator.get_documents_list_query(
            kb_id=str(kb_id),
            file_type=file_type,
            filter=query_filter,
            offset=offset,
            limit=limit,
        )
        rows = await knowledge_base_documents_repository.execute_query(
            sql_query, query_params
        )
        data = [_document_row_to_dict(row) for row in rows]
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data={'resources': data}),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )


# Documents uploaded before index status tracking have no status at all
NOT_TRACKED = 'NOT_TRACKED'


@kb_document_router.get('/v1/knowledge-bases/{kb_id}/index-status')
@inject
async def get_index_status(
    kb_id: uuid.UUID,
    failed_limit: int = Query(
        20, ge=0, le=100, description='How many failed documents to list'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    knowledge_base_documents_repository: SQLAlchemyRepository[
        KnowledgeBaseDocuments
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_documents_repository]),
) -> JSONResponse:
    """How many documents the knowledge base has, how many are in each indexing
    state, and the most recently failed ones with their errors.

    Counted in the database, so it covers every document, not one page.
    """
    if not await knowledge_base_repository.find_one(id=kb_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the given id does not exist'
            ),
        )

    documents = KnowledgeBaseDocuments
    counts = {status_value.value: 0 for status_value in IndexStatus}
    counts[NOT_TRACKED] = 0
    async with knowledge_base_documents_repository.session() as session:
        rows = await session.execute(
            select(documents.index_status, func.count())
            .where(documents.knowledge_base_id == kb_id)
            .group_by(documents.index_status)
        )
        for index_status, count in rows.all():
            counts[index_status or NOT_TRACKED] = count
        failed = (
            await session.execute(
                select(
                    documents.id,
                    documents.file_name,
                    documents.index_error,
                    documents.index_status_updated_at,
                )
                .where(
                    documents.knowledge_base_id == kb_id,
                    documents.index_status == IndexStatus.FAILED.value,
                )
                .order_by(
                    documents.index_status_updated_at.desc().nulls_last(),
                    documents.created_at.desc(),
                )
                .limit(failed_limit)
            )
        ).all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'knowledge_base_id': str(kb_id),
                'total': sum(counts.values()),
                'counts': counts,
                'failed_documents': [
                    {
                        'id': str(row.id),
                        'file_name': row.file_name,
                        'index_error': row.index_error,
                        'index_status_updated_at': row.index_status_updated_at.isoformat()
                        if row.index_status_updated_at
                        else None,
                    }
                    for row in failed
                ],
            }
        ),
    )


@kb_document_router.delete('/v1/knowledge-bases/{kb_id}/documents/{document_id}')
@inject
async def delete_documents(
    kb_id: uuid.UUID,
    document_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_documents_repository: SQLAlchemyRepository[
        KnowledgeBaseDocuments
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_documents_repository]),
    knowledge_base_embeddings_repository: SQLAlchemyRepository[
        KnowledgeBaseEmbeddings
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_embeddings_repository]),
) -> JSONResponse:
    """Delete a document and its associated embeddings from a knowledge base."""
    # Validate document exists
    existing_document = await knowledge_base_documents_repository.find_one(
        id=document_id, knowledge_base_id=kb_id
    )
    if not existing_document:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Document not found for this knowledge base'
            ),
        )

    # Delete document and embeddings
    await knowledge_base_documents_repository.delete_all(
        id=document_id, knowledge_base_id=kb_id
    )
    await knowledge_base_embeddings_repository.delete_all(document_id=document_id)

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Deleted the Knowledge Base Documents and embeddings records successfully',
                'knowledge_base_id': str(kb_id),
            }
        ),
    )


@kb_document_router.get('/v1/knowledge-bases/{kb_id}/document/{document_id}')
@inject
async def get_document_with_id(
    kb_id: uuid.UUID,
    document_id: uuid.UUID,
    signed_url: Optional[bool] = False,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_documents_repository: SQLAlchemyRepository[
        KnowledgeBaseDocuments
    ] = Depends(Provide[KnowledgeBaseContainer.knowledge_base_documents_repository]),
    config: dict = Depends(Provide[KnowledgeBaseContainer.config]),
    cloude_storage_manager: CloudStorageManager = Depends(
        Provide[KnowledgeBaseContainer.cloud_storage_manager]
    ),
) -> JSONResponse:
    """Get a document for a knowledge base by id, optionally returning a signed URL."""
    # Validate document exists
    existing_document = await knowledge_base_documents_repository.find_one(
        id=document_id, knowledge_base_id=kb_id
    )
    if not existing_document:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Document not found for this knowledge base'
            ),
        )
    if signed_url:
        bucket = config['storage']['application_bucket']
        presigned_url = cloude_storage_manager.generate_presigned_url(
            bucket, existing_document.file_path, 'GET'
        )
        response_data = existing_document.to_dict()
        response_data['signed_url'] = presigned_url
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                data={'resources': response_data}
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'resources': existing_document.to_dict()}
        ),
    )
