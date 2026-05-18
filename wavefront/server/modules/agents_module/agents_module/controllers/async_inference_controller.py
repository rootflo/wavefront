from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject, Provide

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
)
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.models.agent_schemas import AgentInferenceRequest
from agents_module.models.workflow_schemas import WorkflowInferenceRequest
from agents_module.utils.auth_utils import extract_auth_credentials
from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)

async_router = APIRouter()


@async_router.post(
    '/v3/agents/{agent_id}/inference', status_code=status.HTTP_202_ACCEPTED
)
@inject
async def async_agent_inference(
    request: Request,
    agent_id: UUID,
    payload: AgentInferenceRequest,
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    logger.info(f'Async agent inference requested for agent_id: {agent_id}')

    access_token, app_key = extract_auth_credentials(request)

    llm_config: Optional[dict] = None
    if payload.llm_inference_config_id:
        llm_config_dict = await llm_inference_config_service.get_config(
            payload.llm_inference_config_id
        )
        if not llm_config_dict:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {payload.llm_inference_config_id}'
                ),
            )
        llm_config = llm_config_dict

    try:
        result = await async_agentic_execution_service.create_and_enqueue_agent(
            agent_id=agent_id,
            inputs=payload.inputs,
            variables=payload.variables,
            output_json_enabled=payload.output_json_enabled,
            access_token=access_token,
            app_key=app_key,
            llm_config=llm_config,
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    logger.info(f'Agent execution enqueued: {result.execution_id}')
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent inference queued successfully',
                'data': result.model_dump(mode='json'),
            }
        ),
    )


@async_router.post(
    '/v3/workflows/{workflow_id}/inference', status_code=status.HTTP_202_ACCEPTED
)
@inject
async def async_workflow_inference(
    request: Request,
    workflow_id: UUID,
    payload: WorkflowInferenceRequest,
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    logger.info(f'Async workflow inference requested for workflow_id: {workflow_id}')

    access_token, app_key = extract_auth_credentials(request)

    try:
        workflow_data = await workflow_crud_service.get_workflow(workflow_id)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    try:
        result = await async_agentic_execution_service.create_and_enqueue_workflow(
            workflow_id=workflow_id,
            workflow_name=workflow_data['name'],
            namespace=workflow_data['namespace'],
            inputs=payload.inputs,
            variables=payload.variables,
            output_json_enabled=payload.output_json_enabled,
            access_token=access_token,
            app_key=app_key,
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    logger.info(f'Workflow execution enqueued: {result.execution_id}')
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow inference queued successfully',
                'data': result.model_dump(mode='json'),
            }
        ),
    )


@async_router.get('/v1/agentic-executions/{execution_id}')
@inject
async def get_execution_status(
    execution_id: UUID,
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await async_agentic_execution_service.get_execution_status(
            execution_id
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Execution status retrieved successfully',
                'data': result.model_dump(mode='json'),
            }
        ),
    )


@async_router.get('/v1/agentic-executions')
@inject
async def list_executions(
    entity_id: Optional[UUID] = Query(
        None, description='Filter by agent or workflow UUID'
    ),
    entity_type: Optional[str] = Query(
        None, description='Filter by entity type: agent or workflow'
    ),
    execution_status: Optional[str] = Query(
        None, alias='status', description='Filter by status'
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    results = await async_agentic_execution_service.list_executions(
        entity_id=entity_id,
        entity_type=entity_type,
        status=execution_status,
        offset=offset,
        limit=limit,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Executions retrieved successfully',
                'data': {
                    'executions': [r.model_dump(mode='json') for r in results],
                    'count': len(results),
                },
            }
        ),
    )
