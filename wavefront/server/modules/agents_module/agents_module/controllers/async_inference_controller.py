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
from agents_module.services.agent_crud_service import AgentCrudService
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.models.agent_schemas import AgentInferenceRequest
from agents_module.models.workflow_schemas import WorkflowInferenceRequest
from agents_module.utils.auth_utils import extract_auth_credentials
from agents_module.utils.input_processing_utils import validate_inference_inputs_media
from user_management_module.utils.user_utils import check_is_admin
from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)

async_router = APIRouter()

_SHOW_ERROR_DESCRIPTION = (
    'Return the stored error text instead of a generic message. Honoured for '
    'admin callers only; everyone else gets the generic message regardless.'
)


async def _may_see_error(request: Request, show_error: bool) -> bool:
    """Both halves must hold: the caller asks, and the caller is an admin.

    Asking is a query param, so on its own it gates nothing — anyone can set
    it. The admin check is what actually restricts the disclosure; the param
    keeps the error text out of the default payload even for admins, so it
    can't reach a UI by accident.
    """
    if not show_error:
        return False

    session = getattr(request.state, 'session', None)
    if session is None:
        return False

    return await check_is_admin(session.role_id)


@async_router.post(
    '/v3/agents/{agent_id}/inference', status_code=status.HTTP_202_ACCEPTED
)
@inject
async def async_agent_inference(
    request: Request,
    agent_id: UUID,
    payload: AgentInferenceRequest,
    version: Optional[int] = Query(
        None, description='Specific agent version to run; defaults to current_version'
    ),
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    logger.info(
        f'Async agent inference requested for agent_id: {agent_id}, version: {version}'
    )

    access_token, app_key = extract_auth_credentials(request)

    # Before the version lookup and before pre_save_binary_inputs uploads
    # anything: an unsupported file should cost the caller a 400, not a 202
    # plus a stored blob and a failed execution.
    validate_inference_inputs_media(payload.inputs)

    # Resolve the concrete version now (rejecting a missing/deleted explicit
    # version) so the enqueued job runs the version observed by this request,
    # not whatever is current when the worker later picks it up.
    try:
        agent_data = await agent_crud_service.get_agent(agent_id, version=version)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    resolved_version = agent_data['version']

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
            version=resolved_version,
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
    version: Optional[int] = Query(
        None,
        description='Specific workflow version to run; defaults to current_version',
    ),
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
    logger.info(
        f'Async workflow inference requested for workflow_id: {workflow_id}, version: {version}'
    )

    access_token, app_key = extract_auth_credentials(request)

    validate_inference_inputs_media(payload.inputs)

    try:
        workflow_data = await workflow_crud_service.get_workflow(
            workflow_id, version=version
        )
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
            version=workflow_data.get('version'),
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
    request: Request,
    execution_id: UUID,
    show_error: bool = Query(False, description=_SHOW_ERROR_DESCRIPTION),
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    include_error = await _may_see_error(request, show_error)

    try:
        result = await async_agentic_execution_service.get_execution_status(
            execution_id, include_error=include_error
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
    request: Request,
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
    show_error: bool = Query(False, description=_SHOW_ERROR_DESCRIPTION),
    async_agentic_execution_service: AsyncAgenticExecutionService = Depends(
        Provide[AgentsContainer.async_agentic_execution_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    include_error = await _may_see_error(request, show_error)

    results, total = await async_agentic_execution_service.list_executions(
        entity_id=entity_id,
        entity_type=entity_type,
        status=execution_status,
        offset=offset,
        limit=limit,
        include_error=include_error,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Executions retrieved successfully',
                'data': {
                    'executions': [r.model_dump(mode='json') for r in results],
                    'count': len(results),
                    'total': total,
                    'offset': offset,
                    'limit': limit,
                },
            }
        ),
    )
