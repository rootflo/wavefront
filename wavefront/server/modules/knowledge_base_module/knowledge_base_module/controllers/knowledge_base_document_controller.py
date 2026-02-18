import asyncio
from datetime import datetime
import os
import re
from typing import Optional
import uuid
import json

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
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
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud.cloud_storage import CloudStorageManager
from pydantic import BaseModel
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


@kb_document_router.post('/v1/knowledge-bases/{kb_id}/documents')
@inject
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    metadata: str = Form(None),
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
        # Safely load the JSON string into a dictionary
        parsed_metadata = None
        if metadata is not None:
            parsed_metadata = json.loads(metadata)

        async with knowledge_base_documents_repository.session() as session:
            new_kb_document = KnowledgeBaseDocuments(
                id=doc_id,
                knowledge_base_id=kb_id,
                file_path=gcs_file_name,
                file_name=file.filename,
                file_type=file.content_type.split('/')[1],
                file_size=file.size,
                metadata_value=parsed_metadata,
            )

            session.add(new_kb_document)
            await session.commit()

        # Upload to cloud storage
        logger.info(f'The data filename is {gcs_file_name}')
        bucket_name = (
            config['gcp']['gcp_asset_storage_bucket']
            if config['cloud_config']['cloud_provider'] == 'gcp'
            else config['aws']['aws_asset_storage_bucket']
        )
        await asyncio.to_thread(
            cloud_storage.save_small_file,
            file_content=file_bytes,
            bucket_name=bucket_name,
            key=gcs_file_name,
            content_type=file.content_type,
        )
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
            topic_id = (
                config['gcp']['email_topic_id']
                if config['cloud_config']['cloud_provider'] == 'gcp'
                else config['aws']['queue_url']
            )
            message_id = message_queue.add_message(
                message_body=data, topic_name_or_queue_url=topic_id
            )
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
        provider = config['cloud_config']['cloud_provider']
        bucket = (
            config['gcp']['gcp_asset_storage_bucket']
            if provider.lower() == 'gcp'
            else config['aws']['aws_asset_storage_bucket']
        )
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
