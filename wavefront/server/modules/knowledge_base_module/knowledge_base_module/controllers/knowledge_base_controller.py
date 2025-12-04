from datetime import datetime
import uuid

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
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
    async with knowledge_base_repository.session() as session:
        new_kb = KnowledgeBase(
            name=new_base.name,
            description=new_base.description,
            type=new_base.type,
            vector_size=new_base.vector_size,
            vector_size_1=new_base.vector_size_1 if new_base.vector_size_1 else None,
        )
        session.add(new_kb)
        await session.flush()
        new_kb_id = new_kb.id
        await session.commit()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Created the knowledge base successfully',
                    'knowledge_base_id': str(new_kb_id),
                }
            ),
        )


@knowledge_base_router.get(
    '/v1/knowledge-bases/{kb_id}', response_model=KnowledgeBaseResponse
)
@inject
async def get_knowledge_bases_id(
    kb_id: uuid.UUID,
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
) -> KnowledgeBaseResponse:
    """Get knowledge base by ID."""
    fetch_knowledge_base_id = await knowledge_base_repository.find_one(id=kb_id)
    if not fetch_knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge Base with the mentioned id doesn't exist",
        )

    return KnowledgeBaseResponse(
        id=fetch_knowledge_base_id.id,
        name=fetch_knowledge_base_id.name,
        description=fetch_knowledge_base_id.description,
        type=fetch_knowledge_base_id.type,
        created_at=fetch_knowledge_base_id.created_at,
        updated_at=fetch_knowledge_base_id.updated_at,
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


@knowledge_base_router.put('/v1/knowledge-bases/{kb_id}')
@inject
async def update_knowledge_bases(
    kb_id: uuid.UUID,
    new_base: NewKnowledge,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
) -> JSONResponse:
    """Update an existing knowledge base."""
    existing_kb = await knowledge_base_repository.find_one(id=kb_id)
    if not existing_kb:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                "Knowledge Base with the given id doesn't exist"
            ),
        )

    await knowledge_base_repository.find_one_and_update(
        {'id': kb_id},
        name=new_base.name,
        description=new_base.description,
        type=new_base.type,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Updated the Knowledge Base successfully',
                'knowledge_base_id': str(kb_id),
            }
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

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Deleted the Knowledge Base successfully',
                'knowledge_base_id': str(kb_id),
            }
        ),
    )
