from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide

from agents_module.agents_container import AgentsContainer
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.workflow_pipeline import WorkflowPipeline
from db_repo_module.models.workflow_runs import WorkflowRuns
from db_repo_module.models.workflow import Workflow
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from flo_cloud.message_queue import MessageQueueManager
from datetime import datetime
from flo_utils.constants.workflow import WorkflowStatus
import uuid

workflow_pipeline_router = APIRouter(prefix='/v1')


class CreateWorkflowPipelinePayload(BaseModel):
    name: str
    description: Optional[str] = None
    workflow_id: uuid.UUID
    retry_policy: Optional[str] = None
    timeout: Optional[int] = None
    concurrency_limit: Optional[int] = None


class UpdateWorkflowPipelinePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workflow_id: Optional[uuid.UUID] = None
    retry_policy: Optional[str] = None
    timeout: Optional[int] = None
    concurrency_limit: Optional[int] = None


class WorkflowMessage(BaseModel):
    inputs: List[dict] | str = Field(
        ...,
        description='Inputs to use for inference',
        example=[
            'Process the following text: <text_to_process> with <target_language>'
        ],
    )
    variables: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Variables to pass to the workflow during inference',
        example={
            'target_language': 'Spanish',
            'tone': 'formal',
            'text_to_process': 'Welcome to our application',
        },
    )


class SubmitWorkflowPipelinePayload(BaseModel):
    pipeline_job: WorkflowMessage


@workflow_pipeline_router.post('/workflow-pipelines')
@inject
async def create_workflow_pipeline(
    create_workflow_pipeline_payload: CreateWorkflowPipelinePayload,
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    workflow_repository: SQLAlchemyRepository[Workflow] = Depends(
        Provide[AgentsContainer.workflow_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    # Verify workflow exists
    workflow = await workflow_repository.find_one(
        id=create_workflow_pipeline_payload.workflow_id
    )
    if not workflow:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Workflow not found with ID: {create_workflow_pipeline_payload.workflow_id}'
            ),
        )

    created_workflow_pipeline = await workflow_pipeline_repository.create(
        name=create_workflow_pipeline_payload.name,
        description=create_workflow_pipeline_payload.description,
        workflow_id=create_workflow_pipeline_payload.workflow_id,
        retry_policy=create_workflow_pipeline_payload.retry_policy,
        timeout=create_workflow_pipeline_payload.timeout,
        concurrency_limit=create_workflow_pipeline_payload.concurrency_limit,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow pipeline created successfully',
                'workflow_pipeline_id': str(created_workflow_pipeline.id),
            }
        ),
    )


@workflow_pipeline_router.post('/workflow-pipelines/{workflow_pipeline_id}/submit')
@inject
async def submit_workflow_to_pipeline(
    workflow_pipeline_id: str,
    submit_workflow_pipeline_payload: SubmitWorkflowPipelinePayload,
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    workflow_run_repository: SQLAlchemyRepository[WorkflowRuns] = Depends(
        Provide[AgentsContainer.workflow_runs_repository]
    ),
    workflow_repository: SQLAlchemyRepository[Workflow] = Depends(
        Provide[AgentsContainer.workflow_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    message_queue_manager: MessageQueueManager = Depends(
        Provide[AgentsContainer.message_queue_manager]
    ),
    config: dict[str, Any] = Depends(Provide[AgentsContainer.config]),
):
    workflow_pipeline = await workflow_pipeline_repository.find_one(
        id=workflow_pipeline_id
    )

    if not workflow_pipeline:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Workflow pipeline not found'
            ),
        )

    workflow = await workflow_repository.find_one(id=workflow_pipeline.workflow_id)

    if not workflow:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Workflow not found for this pipeline'
            ),
        )

    workflow_run = await workflow_run_repository.create(
        workflow_pipeline_id=workflow_pipeline_id,
        start_time=datetime.now(),
        status=WorkflowStatus.INITIATED,
    )

    workflow_run_id = str(workflow_run.id)

    pipeline_job_payload = submit_workflow_pipeline_payload.model_dump(mode='json')
    message_queue_manager.add_message(
        message_body={
            'workflow_run_id': workflow_run_id,
            'workflow_pipeline_id': workflow_pipeline_id,
            'pipeline_job': pipeline_job_payload['pipeline_job'],
            'workflow_data': workflow.to_dict(),
        },
        topic_name_or_queue_url=config['workflow']['worker_topic'],
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Request submitted to workflow pipeline',
                'workflow_run_id': workflow_run_id,
            }
        ),
    )


@workflow_pipeline_router.get('/workflow-pipelines')
@inject
async def get_workflow_pipelines(
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    workflow_pipelines = await workflow_pipeline_repository.find()
    workflow_pipelines_list = [
        workflow_pipeline.to_dict() for workflow_pipeline in workflow_pipelines
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'workflow_pipelines': workflow_pipelines_list}
        ),
    )


@workflow_pipeline_router.get('/workflow-pipelines/{workflow_pipeline_id}')
@inject
async def get_workflow_pipeline(
    workflow_pipeline_id: str,
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    workflow_pipeline = await workflow_pipeline_repository.find_one(
        id=workflow_pipeline_id
    )
    if not workflow_pipeline:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Workflow pipeline not found'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(workflow_pipeline.to_dict()),
    )


@workflow_pipeline_router.put('/workflow-pipelines/{workflow_pipeline_id}')
@inject
async def update_workflow_pipeline(
    workflow_pipeline_id: str,
    update_workflow_pipeline_payload: UpdateWorkflowPipelinePayload,
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    workflow_repository: SQLAlchemyRepository[Workflow] = Depends(
        Provide[AgentsContainer.workflow_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    existing_workflow_pipeline = await workflow_pipeline_repository.find_one(
        id=workflow_pipeline_id
    )
    if not existing_workflow_pipeline:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Workflow pipeline not found'
            ),
        )

    # If workflow_id is being updated, verify it exists
    if update_workflow_pipeline_payload.workflow_id:
        workflow = await workflow_repository.find_one(
            id=update_workflow_pipeline_payload.workflow_id
        )
        if not workflow:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'Workflow not found with ID: {update_workflow_pipeline_payload.workflow_id}'
                ),
            )

    await workflow_pipeline_repository.find_one_and_update(
        filters={'id': workflow_pipeline_id},
        name=update_workflow_pipeline_payload.name,
        description=update_workflow_pipeline_payload.description,
        workflow_id=update_workflow_pipeline_payload.workflow_id,
        retry_policy=update_workflow_pipeline_payload.retry_policy,
        timeout=update_workflow_pipeline_payload.timeout,
        concurrency_limit=update_workflow_pipeline_payload.concurrency_limit,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow pipeline updated successfully',
                'workflow_pipeline_id': workflow_pipeline_id,
            }
        ),
    )


@workflow_pipeline_router.delete('/workflow-pipelines/{workflow_pipeline_id}')
@inject
async def delete_workflow_pipeline(
    workflow_pipeline_id: str,
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    deleted_workflow_pipeline = await workflow_pipeline_repository.delete_all(
        id=workflow_pipeline_id
    )
    if not deleted_workflow_pipeline:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Workflow pipeline not found'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow pipeline deleted successfully',
                'workflow_pipeline_id': workflow_pipeline_id,
            }
        ),
    )
