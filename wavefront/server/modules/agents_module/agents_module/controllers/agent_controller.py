from uuid import UUID
from fastapi import APIRouter, Depends, status, Path, Request, Query
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject, Provide

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.agent_crud_service import AgentCrudService
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from llm_inference_config_module.container import LlmInferenceConfigContainer
from agents_module.models.agent_schemas import (
    AgentInferenceRequest,
    AgentInferenceResponse,
)
from agents_module.utils.input_processing_utils import process_inference_inputs
from agents_module.utils.auth_utils import extract_auth_credentials
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)
from tools_module.registry.tool_loader import ToolLoader
from flo_ai import FloUtils

agents_router = APIRouter()


@agents_router.post(
    '/v1/agents/{namespace}/{agent_id}/inference', response_model=AgentInferenceResponse
)
@inject
async def agent_inference(
    request: Request,
    namespace: str = Path(..., description='The namespace of the agent'),
    agent_id: str = Path(..., description='The ID of the agent to run inference with'),
    agent_inference_payload: AgentInferenceRequest = ...,
    agent_inference_service: AgentInferenceService = Depends(
        Provide[AgentsContainer.agent_inference_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    """
    Run inference using a flo_ai agent

    This endpoint:
    1. Fetches the agent YAML configuration from cloud storage using namespace and agent_id as key (agents/{namespace}/{agent_id}.yaml)
    2. Creates an agent instance from the YAML using flo_ai.AgentBuilder
    3. Runs inference with the provided variables
    4. Returns the result along with execution metadata

    Args:
        namespace: The namespace of the agent
        agent_id: The unique identifier for the agent
        agent_inference_payload: AgentInferenceRequest containing variables for the agent

    Returns:
        AgentInferenceResponse: Contains the inference result and metadata

    """
    logger.info(f'Starting inference for namespace: {namespace}, agent_id: {agent_id}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Fetch LLM config if provided
    llm_config = None
    if agent_inference_payload.llm_inference_config_id:
        llm_config_dict = await llm_inference_config_service.get_config(
            agent_inference_payload.llm_inference_config_id
        )
        if not llm_config_dict:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {agent_inference_payload.llm_inference_config_id}'
                ),
            )
        else:
            llm_config = LlmInferenceConfig(**llm_config_dict)

    # Process inputs using common utility function
    resolved_inputs = process_inference_inputs(agent_inference_payload.inputs)

    # Perform the complete inference workflow
    result, execution_time = await agent_inference_service.perform_inference(
        agent_id=agent_id,
        namespace=namespace,
        variables=agent_inference_payload.variables or {},
        inputs=resolved_inputs,
        llm_config=llm_config,
        output_json_enabled=agent_inference_payload.output_json_enabled,
        access_token=access_token,
        app_key=app_key,
    )

    response_data = AgentInferenceResponse(
        result=result[-1].content,
        agent_id=agent_id,
        namespace=namespace,
        execution_time=execution_time,
    )

    logger.info(
        f'Successfully completed inference for namespace: {namespace}, agent_id: {agent_id}'
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent inference completed successfully',
                'data': response_data.model_dump(),
            }
        ),
    )


@agents_router.post(
    '/v2/agents/{agent_id}/inference', response_model=AgentInferenceResponse
)
@inject
async def agent_inference_v2(
    request: Request,
    agent_inference_payload: AgentInferenceRequest,
    agent_id: UUID = Path(
        ..., description='The UUID of the agent to run inference with'
    ),
    agent_inference_service: AgentInferenceService = Depends(
        Provide[AgentsContainer.agent_inference_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    """
    Run inference using a flo_ai agent (v2 - UUID-based)

    This endpoint:
    1. Fetches the agent from DB by UUID
    2. Retrieves YAML configuration from cloud storage
    3. Creates an agent instance from the YAML using flo_ai.AgentBuilder
    4. Runs inference with the provided variables
    5. Returns the result along with execution metadata

    Args:
        agent_id: The UUID of the agent
        request: Request containing variables for the agent

    Returns:
        AgentInferenceResponse: Contains the inference result and metadata
    """
    logger.info(f'Starting v2 inference for agent_id: {agent_id}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Fetch LLM config if provided
    llm_config = None
    if agent_inference_payload.llm_inference_config_id:
        llm_config_dict = await llm_inference_config_service.get_config(
            agent_inference_payload.llm_inference_config_id
        )
        if not llm_config_dict:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {agent_inference_payload.llm_inference_config_id}'
                ),
            )
        else:
            llm_config = LlmInferenceConfig(**llm_config_dict)

    # Process inputs using common utility function
    resolved_inputs = process_inference_inputs(agent_inference_payload.inputs)

    try:
        # Perform the complete inference workflow (v2)
        (
            result,
            execution_time,
            namespace,
        ) = await agent_inference_service.perform_inference_v2(
            agent_id=agent_id,
            variables=agent_inference_payload.variables or {},
            inputs=resolved_inputs
            if isinstance(resolved_inputs, list)
            else [resolved_inputs],
            llm_config=llm_config,
            output_json_enabled=agent_inference_payload.output_json_enabled,
            access_token=access_token,
            app_key=app_key,
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    if agent_inference_payload.output_json_enabled:
        result = FloUtils.extract_jsons_from_string(result[-1].content)
    else:
        result = result[-1].content

    response_data = AgentInferenceResponse(
        result=result,
        agent_id=str(agent_id),
        namespace=namespace,
        execution_time=execution_time,
    )

    logger.info(f'Successfully completed v2 inference for agent_id: {agent_id}')

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent inference completed successfully',
                'data': response_data.model_dump(),
            }
        ),
    )


@agents_router.post('/v1/agent-management/agents/{name}')
@inject
async def create_agent(
    request: Request,
    name: str = Path(..., description='The name of the agent to create'),
    namespace: str = Query('default', description='The namespace for the agent'),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_loader: ToolLoader = Depends(Provide[AgentsContainer.tool_loader]),
):
    """
    Create a new agent

    Args:
        name: The agent name (unique globally)
        namespace: The namespace (defaults to 'default', created if doesn't exist)
        request: Request containing raw YAML content as text/plain

    Returns:
        JSONResponse: Success or error response with agent details
    """
    logger.info(f'Creating agent - namespace: {namespace}, name: {name}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Read raw YAML content from request body
    yaml_content = (await request.body()).decode('utf-8')

    agent = await agent_crud_service.create_agent(
        name=name,
        namespace=namespace,
        yaml_content=yaml_content,
        tool_available=tool_loader.load_all_tools(),
        access_token=access_token,
        app_key=app_key,
    )

    logger.info(f'Successfully created agent - namespace: {namespace}, name: {name}')
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent created successfully',
                'data': agent,
            }
        ),
    )


@agents_router.get('/v1/agent-management/agents/{agent_id}')
@inject
async def get_agent(
    agent_id: UUID = Path(..., description='The UUID of the agent to retrieve'),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get agent by UUID with YAML configuration

    Args:
        agent_id: The agent UUID

    Returns:
        JSONResponse: Agent details including YAML content
    """
    logger.info(f'Getting agent by ID: {agent_id}')

    agent = await agent_crud_service.get_agent(agent_id)

    logger.info(f'Successfully retrieved agent - ID: {agent_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent retrieved successfully',
                'data': agent,
            }
        ),
    )


@agents_router.put('/v1/agent-management/agents/{agent_id}')
@inject
async def update_agent(
    request: Request,
    agent_id: UUID = Path(..., description='The UUID of the agent to update'),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_loader: ToolLoader = Depends(Provide[AgentsContainer.tool_loader]),
):
    """
    Update existing agent YAML configuration

    Args:
        agent_id: The agent UUID
        request: Request containing raw YAML content as text/plain

    Returns:
        JSONResponse: Success or error response with updated agent details
    """
    logger.info(f'Updating agent - ID: {agent_id}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Read raw YAML content from request body
    yaml_content = (await request.body()).decode('utf-8')

    agent = await agent_crud_service.update_agent(
        agent_id=agent_id,
        yaml_content=yaml_content,
        tool_available=tool_loader.load_all_tools(),
        access_token=access_token,
        app_key=app_key,
    )

    logger.info(f'Successfully updated agent - ID: {agent_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent updated successfully',
                'data': agent,
            }
        ),
    )


@agents_router.get('/v1/agent-management/agents')
@inject
async def list_agents(
    namespace: str | None = Query(
        None, description='Optional namespace to filter agents'
    ),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    List agents with optional namespace filtering

    Args:
        namespace: Optional namespace to filter agents (returns all if not provided)

    Returns:
        JSONResponse: List of agents (without YAML content)
    """
    logger.info(f'Listing agents - namespace filter: {namespace}')

    agents_list = await agent_crud_service.list_agents(namespace=namespace)

    logger.info(f'Successfully retrieved {len(agents_list)} agents')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agents retrieved successfully',
                'data': {'agents': agents_list, 'count': len(agents_list)},
            }
        ),
    )


@agents_router.delete('/v1/agent-management/agents/{agent_id}')
@inject
async def delete_agent(
    agent_id: UUID = Path(..., description='The UUID of the agent to delete'),
    agent_crud_service: AgentCrudService = Depends(
        Provide[AgentsContainer.agent_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Delete an agent by UUID

    Args:
        agent_id: The agent UUID

    Returns:
        JSONResponse: Success or error response
    """
    logger.info(f'Deleting agent - ID: {agent_id}')

    await agent_crud_service.delete_agent(agent_id)

    logger.info(f'Successfully deleted agent - ID: {agent_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Agent deleted successfully',
                'data': {'agent_id': str(agent_id)},
            }
        ),
    )
