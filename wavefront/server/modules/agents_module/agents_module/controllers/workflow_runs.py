from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject, Provide
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.workflow_runs import WorkflowRuns
from agents_module.agents_container import AgentsContainer
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy import select, desc
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer

workflow_runs_router = APIRouter(prefix='/v1')


class CreateWorkflowRunPayload(BaseModel):
    workflow_pipeline_id: str
    status: Optional[str] = None
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    output: Optional[str] = None


class UpdateWorkflowRunPayload(BaseModel):
    status: Optional[str] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    output: Optional[str] = None


@workflow_runs_router.post('/workflow-runs')
@inject
async def create_workflow_run(
    create_workflow_run_payload: CreateWorkflowRunPayload,
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    created_workflow_run = await workflow_run_repository.create(
        workflow_pipeline_id=create_workflow_run_payload.workflow_pipeline_id,
        status=create_workflow_run_payload.status,
        start_time=create_workflow_run_payload.start_time,
        end_time=create_workflow_run_payload.end_time,
        error=create_workflow_run_payload.error,
        output=create_workflow_run_payload.output,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow run created successfully',
                'workflow_run_id': str(created_workflow_run.id),
            }
        ),
    )


@workflow_runs_router.get('/workflow-runs')
@inject
async def get_workflow_runs(
    workflow_pipeline_id: Optional[str] = None,
    workflow_status: Optional[str] = None,
    offset: Optional[int] = Query(0, ge=0, description='The number of items to skip'),
    limit: Optional[int] = Query(
        100, ge=1, le=2000, description='The maximum number of items to return'
    ),
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    filters = {}
    if workflow_pipeline_id:
        filters['workflow_pipeline_id'] = workflow_pipeline_id
    if workflow_status:
        filters['status'] = workflow_status

    # Get paginated results using session to ensure offset is applied
    async with workflow_run_repository.session() as session:
        query = select(WorkflowRuns)
        for key, value in filters.items():
            if isinstance(value, list):
                query = query.where(getattr(WorkflowRuns, key).in_(value))
            else:
                query = query.where(getattr(WorkflowRuns, key) == value)
        query = query.order_by(desc(WorkflowRuns.end_time)).offset(offset).limit(limit)
        result = await session.execute(query)
        workflow_runs = result.scalars().all()

    workflow_runs_list = [workflow_run.to_dict() for workflow_run in workflow_runs]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'workflow_runs': workflow_runs_list,
            }
        ),
    )


@workflow_runs_router.get('/workflow-runs/{workflow_run_id}')
@inject
async def get_workflow_run(
    workflow_run_id: str,
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    workflow_run = await workflow_run_repository.find_one(id=workflow_run_id)
    if not workflow_run:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('Workflow run not found'),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'workflow_run': workflow_run.to_dict()}
        ),
    )


@workflow_runs_router.put('/workflow-runs/{workflow_run_id}')
@inject
async def update_workflow_run(
    workflow_run_id: str,
    update_workflow_run_payload: UpdateWorkflowRunPayload,
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    existing_workflow_run = await workflow_run_repository.find_one(id=workflow_run_id)
    if not existing_workflow_run:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('Workflow run not found'),
        )

    await workflow_run_repository.find_one_and_update(
        filters={'id': workflow_run_id},
        **{
            'status': update_workflow_run_payload.status,
            'end_time': update_workflow_run_payload.end_time,
            'error': update_workflow_run_payload.error,
            'output': update_workflow_run_payload.output,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow run updated successfully',
                'workflow_run_id': workflow_run_id,
            }
        ),
    )


@workflow_runs_router.delete('/workflow-runs/{workflow_run_id}')
@inject
async def delete_workflow_run(
    workflow_run_id: str,
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    deleted_workflow_run = await workflow_run_repository.delete_all(id=workflow_run_id)
    if not deleted_workflow_run:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('Workflow run not found'),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow run deleted successfully',
                'workflow_run_id': workflow_run_id,
            }
        ),
    )
