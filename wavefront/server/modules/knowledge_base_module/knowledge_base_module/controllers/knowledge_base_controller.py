from datetime import datetime
import uuid

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.application_cache import (
    invalidate_knowledge_bases_cache,
)
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.models.knowledge_base_schema import NewKnowledge
from knowledge_base_module.models.knowledge_base_schema import UpdateKnowledge
from pydantic import BaseModel
from sqlalchemy import Result
from sqlalchemy import select

knowledge_base_router = APIRouter()


class KnowledgeBaseResponse(BaseModel):
    """Response model for knowledge base data."""

    id: uuid.UUID
    name: str
    description: str
    type: str
    created_at: datetime
    updated_at: datetime


@knowledge_base_router.post('/v1/knowledge-bases')
@inject
async def create_knowledge_base(
    new_base: NewKnowledge,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    cache_manager: CacheManager = Depends(
        Provide[KnowledgeBaseContainer.cache_manager]
    ),
) -> JSONResponse:
    """Create a new knowledge base."""
    # Check for existing knowledge base
    existing_knowledge_base = await knowledge_base_repository.find_one(
        name=new_base.name
    )
    if existing_knowledge_base:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Knowledge Base with the same name already exists'
            ),
        )

    # Create new knowledge base
    new_kb = await knowledge_base_repository.create(
        name=new_base.name,
        description=new_base.description,
        type=new_base.type,
        vector_size=new_base.vector_size,
        vector_size_1=new_base.vector_size_1 if new_base.vector_size_1 else None,
    )
    invalidate_knowledge_bases_cache(cache_manager)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'id': str(new_kb.id),
                'name': new_kb.name,
                'created_at': new_kb.created_at.isoformat(),
                'updated_at': new_kb.updated_at.isoformat(),
            }
        ),
    )


@knowledge_base_router.get('/v1/knowledge-bases/{kb_id}')
@inject
async def get_knowledge_bases_id(
    kb_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
) -> JSONResponse:
    """Get knowledge base by ID."""
    fetch_knowledge_base_id = await knowledge_base_repository.find_one(id=kb_id)
    if not fetch_knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge Base with the mentioned id doesn't exist",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data=fetch_knowledge_base_id.to_dict()
        ),
    )


@knowledge_base_router.get('/v1/knowledge-bases')
@inject
async def get_knowledge_bases(
    offset: int = Query(0, ge=0, description='The number of items to skip'),
    limit: int = Query(
        10, ge=1, le=100, description='The maximum number of items to return'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
) -> JSONResponse:
    """Get all knowledge bases with pagination."""
    async with knowledge_base_repository.session() as session:
        sql = select(KnowledgeBase).slice(offset, limit)
        results: Result = await session.execute(sql)
        resources = results.scalars().all()
        data = [res.to_dict() for res in resources]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(data={'resources': data}),
        )


@knowledge_base_router.patch('/v1/knowledge-bases/{kb_id}')
@inject
async def update_knowledge_bases(
    kb_id: uuid.UUID,
    update_base: UpdateKnowledge,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    cache_manager: CacheManager = Depends(
        Provide[KnowledgeBaseContainer.cache_manager]
    ),
) -> JSONResponse:
    """Partially update an existing knowledge base."""
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                "Knowledge Base with the given id doesn't exist"
            ),
        )

    update_kwargs = {}
    if update_base.name is not None:
        if update_base.name != existing_kb.name:
            duplicate_kb = await knowledge_base_repository.find_one(
                name=update_base.name
            )
            if duplicate_kb:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'Knowledge Base with the same name already exists'
                    ),
                )
        update_kwargs['name'] = update_base.name
    if update_base.description is not None:
        update_kwargs['description'] = update_base.description
    if update_base.type is not None:
        update_kwargs['type'] = update_base.type

    if not update_kwargs:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No fields provided to update'
            ),
        )

    update_kwargs['updated_at'] = datetime.now()
    updated_kb = await knowledge_base_repository.find_one_and_update(
        {'id': kb_id},
        refresh=True,
        **update_kwargs,
    )
    invalidate_knowledge_bases_cache(cache_manager)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data=updated_kb.to_dict() if updated_kb else {'id': str(kb_id)}
        ),
    )


@knowledge_base_router.delete('/v1/knowledge-bases/{kb_id}')
@inject
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    cache_manager: CacheManager = Depends(
        Provide[KnowledgeBaseContainer.cache_manager]
    ),
) -> JSONResponse:
    """Delete a knowledge base."""
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                "Knowledge Base with the given id doesn't exist"
            ),
        )

    await knowledge_base_repository.delete_all(id=kb_id)
    invalidate_knowledge_bases_cache(cache_manager)

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Deleted the Knowledge Base successfully',
                'knowledge_base_id': str(kb_id),
            }
        ),
    )
