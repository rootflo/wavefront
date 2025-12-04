from uuid import UUID
from agents_module.utils.input_processing_utils import process_inference_inputs
from agents_module.utils.auth_utils import extract_auth_credentials
from fastapi import APIRouter, Depends, status, Path, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from dependency_injector.wiring import inject, Provide
import json
import asyncio

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from agents_module.services.workflow_events import (
    event_streamer,
    create_workflow_event_callback,
    DEFAULT_EVENTS_FILTER,
)
from agents_module.models.workflow_schemas import (
    WorkflowInferenceRequest,
    WorkflowInferenceResponse,
)
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.workflow_pipeline import WorkflowPipeline

workflows_router = APIRouter()


@workflows_router.post(
    '/v1/workflows/{namespace}/{workflow_id}/inference',
    response_model=WorkflowInferenceResponse,
)
@inject
async def workflow_inference(
    request: Request,
    namespace: str = Path(..., description='The namespace of the workflow'),
    workflow_id: str = Path(
        ..., description='The ID of the workflow to run inference with'
    ),
    request_body: WorkflowInferenceRequest = ...,
    listen_events: bool = Query(
        False, description='Enable real-time event streaming via WebSocket'
    ),
    workflow_inference_service: WorkflowInferenceService = Depends(
        Provide[AgentsContainer.workflow_inference_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Run inference using a flo_ai workflow with optional real-time event streaming

    This endpoint:
    1. Fetches the workflow YAML configuration from cloud storage using namespace and workflow_id as key (workflows/{namespace}/{workflow_id}.yaml)
    2. Creates a workflow instance from the YAML using flo_ai.AriumBuilder
    3. Runs inference with the provided variables
    4. Optionally streams real-time events to connected WebSocket clients
    5. Returns the result along with execution metadata

    Args:
        request: FastAPI request object for extracting user_id
        namespace: The namespace of the workflow
        workflow_id: The unique identifier for the workflow
        request_body: Request containing variables and inputs for the workflow
        listen_events: Whether to enable real-time event streaming

    Returns:
        WorkflowInferenceResponse: Contains the inference result and metadata

    """
    logger.info(
        f'Starting inference for namespace: {namespace}, workflow_id: {workflow_id}, listen_events: {listen_events}'
    )

    # Extract user_id from authenticated session
    user_id = request.state.session.user_id

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    resolved_inputs = process_inference_inputs(request_body.inputs)
    logger.info(f'Inputs to workflow: {resolved_inputs}')

    # Prepare event streaming if requested
    event_callback = None
    events_filter = None

    if listen_events or request_body.listen_events:
        event_callback = create_workflow_event_callback(user_id, namespace, workflow_id)
        events_filter = DEFAULT_EVENTS_FILTER
        logger.info(
            f'Event streaming enabled for user {user_id}, workflow {namespace}/{workflow_id}'
        )

    # Check if streaming is requested
    if listen_events or request_body.listen_events:
        logger.info(
            f'Streaming inference for user {user_id}, workflow {namespace}/{workflow_id}'
        )

        # Get or create event queue for this user-workflow
        event_queue = event_streamer.get_or_create_queue(
            user_id, namespace, workflow_id
        )

        async def generate_inference_stream():
            """Generate streaming inference with events and final output"""
            try:
                # Start inference in background task
                inference_task = asyncio.create_task(
                    workflow_inference_service.perform_inference(
                        workflow_name=workflow_id,
                        namespace=namespace,
                        variables=request_body.variables or {},
                        inputs=resolved_inputs
                        if isinstance(resolved_inputs, list)
                        else [resolved_inputs],
                        output_json_enabled=request_body.output_json_enabled,
                        event_callback=event_callback,
                        events_filter=events_filter,
                        access_token=access_token,
                        app_key=app_key,
                    )
                )

                # Stream events while workflow is running
                workflow_completed = False
                while not workflow_completed and not inference_task.done():
                    try:
                        # Wait for event with timeout
                        event_data = await asyncio.wait_for(
                            event_queue.get(), timeout=1.0
                        )
                        yield f'data: {json.dumps(event_data)}\n\n'
                        await asyncio.sleep(0.1)  # remove it later

                        # Check if workflow ended
                        if event_data.get('event_type') in [
                            'workflow_completed',
                            'workflow_failed',
                        ]:
                            workflow_completed = True

                    except asyncio.TimeoutError:
                        # Continue waiting if no events
                        continue

                # Wait for inference to complete and get result
                result, execution_time = await inference_task

                # Send final output event
                output_event = {
                    'event_type': 'output',
                    'result': result,
                    'workflow_id': workflow_id,
                    'namespace': namespace,
                    'execution_time': execution_time,
                    'timestamp': asyncio.get_event_loop().time(),
                }
                yield f'data: {json.dumps(output_event)}\n\n'
                await asyncio.sleep(0.1)  # remove it later

                logger.info(
                    f'Streaming inference completed for user {user_id}, workflow {namespace}/{workflow_id}'
                )

            except Exception as e:
                logger.error(
                    f'Error in streaming inference for user {user_id}, workflow {namespace}/{workflow_id}: {e}'
                )
                error_event = {
                    'event_type': 'error',
                    'error': str(e),
                    'timestamp': asyncio.get_event_loop().time(),
                }
                yield f'data: {json.dumps(error_event)}\n\n'
            finally:
                # Clean up queue
                event_streamer.cleanup_queue(user_id, namespace, workflow_id)

        return StreamingResponse(
            generate_inference_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'text/event-stream',
                'Transfer-Encoding': 'chunked',
                'X-Accel-Buffering': 'no',  # Disable nginx buffering
            },
        )

    else:
        # Non-streaming mode - normal JSON response
        result, execution_time = await workflow_inference_service.perform_inference(
            workflow_name=workflow_id,
            namespace=namespace,
            variables=request_body.variables or {},
            inputs=resolved_inputs
            if isinstance(resolved_inputs, list)
            else [resolved_inputs],
            output_json_enabled=request_body.output_json_enabled,
            event_callback=event_callback,
            events_filter=events_filter,
            access_token=access_token,
            app_key=app_key,
        )

        response_data = WorkflowInferenceResponse(
            result=result,
            workflow_id=workflow_id,
            namespace=namespace,
            execution_time=execution_time,
        )

        logger.info(
            f'Successfully completed inference for namespace: {namespace}, workflow_id: {workflow_id}'
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Workflow inference completed successfully',
                    'data': response_data.model_dump(),
                }
            ),
        )


@workflows_router.post(
    '/v2/workflows/{workflow_id}/inference',
    response_model=WorkflowInferenceResponse,
)
@inject
async def workflow_inference_v2(
    request: Request,
    workflow_id: UUID = Path(
        ..., description='The UUID of the workflow to run inference with'
    ),
    request_body: WorkflowInferenceRequest = ...,
    listen_events: bool = Query(
        False, description='Enable real-time event streaming via WebSocket'
    ),
    workflow_inference_service: WorkflowInferenceService = Depends(
        Provide[AgentsContainer.workflow_inference_service]
    ),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Run inference using a flo_ai workflow with optional real-time event streaming (v2 - UUID-based)

    This endpoint:
    1. Fetches the workflow from DB by UUID
    2. Retrieves YAML configuration from cloud storage
    3. Creates a workflow instance from the YAML using flo_ai.AriumBuilder
    4. Runs inference with the provided variables
    5. Optionally streams real-time events to connected WebSocket clients
    6. Returns the result along with execution metadata

    Args:
        request: FastAPI request object for extracting user_id
        workflow_id: The UUID of the workflow
        request_body: Request containing variables and inputs for the workflow
        listen_events: Whether to enable real-time event streaming

    Returns:
        WorkflowInferenceResponse: Contains the inference result and metadata
    """
    logger.info(
        f'Starting v2 inference for workflow_id: {workflow_id}, listen_events: {listen_events}'
    )

    # Extract user_id from authenticated session
    user_id = request.state.session.user_id

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Fetch workflow from DB first to get namespace and name
    workflow_data = await workflow_crud_service.get_workflow(workflow_id)
    namespace = workflow_data['namespace']
    workflow_name = workflow_data['name']

    resolved_inputs = process_inference_inputs(request_body.inputs)
    logger.info(f'Inputs to workflow: {resolved_inputs}')

    # Prepare event streaming if requested
    event_callback = None
    events_filter = None

    if listen_events or request_body.listen_events:
        # Use real namespace and workflow name for event streaming
        event_callback = create_workflow_event_callback(
            user_id, namespace, workflow_name
        )
        events_filter = DEFAULT_EVENTS_FILTER
        logger.info(
            f'Event streaming enabled for user {user_id}, workflow {namespace}/{workflow_name}'
        )

    # Check if streaming is requested
    if listen_events or request_body.listen_events:
        logger.info(
            f'Streaming inference for user {user_id}, workflow {namespace}/{workflow_name}'
        )

        # Get or create event queue for this user-workflow
        event_queue = event_streamer.get_or_create_queue(
            user_id, namespace, workflow_name
        )

        async def generate_inference_stream():
            """Generate streaming inference with events and final output"""
            try:
                # Start inference in background task
                inference_task = asyncio.create_task(
                    workflow_inference_service.perform_inference_v2(
                        workflow_data=workflow_data,
                        variables=request_body.variables or {},
                        inputs=resolved_inputs
                        if isinstance(resolved_inputs, list)
                        else [resolved_inputs],
                        output_json_enabled=request_body.output_json_enabled,
                        event_callback=event_callback,
                        events_filter=events_filter,
                        access_token=access_token,
                        app_key=app_key,
                    )
                )

                # Stream events while workflow is running
                workflow_completed = False
                while not workflow_completed and not inference_task.done():
                    try:
                        # Wait for event with timeout
                        event_data = await asyncio.wait_for(
                            event_queue.get(), timeout=1.0
                        )
                        yield f'data: {json.dumps(event_data)}\n\n'
                        await asyncio.sleep(0.1)  # remove it later

                        # Check if workflow ended
                        if event_data.get('event_type') in [
                            'workflow_completed',
                            'workflow_failed',
                        ]:
                            workflow_completed = True

                    except asyncio.TimeoutError:
                        # Continue waiting if no events
                        continue

                # Wait for inference to complete and get result
                result, execution_time = await inference_task

                # Send final output event
                output_event = {
                    'event_type': 'output',
                    'result': result,
                    'workflow_id': workflow_name,
                    'namespace': namespace,
                    'execution_time': execution_time,
                    'timestamp': asyncio.get_event_loop().time(),
                }
                yield f'data: {json.dumps(output_event)}\n\n'
                await asyncio.sleep(0.1)  # remove it later

                logger.info(
                    f'Streaming inference completed for user {user_id}, workflow {namespace}/{workflow_name}'
                )

            except ValueError as e:
                logger.error(f'Error in streaming inference: {e}')
                error_event = {
                    'event_type': 'error',
                    'error': str(e),
                    'timestamp': asyncio.get_event_loop().time(),
                }
                yield f'data: {json.dumps(error_event)}\n\n'
            except Exception as e:
                logger.error(f'Error in streaming inference: {e}')
                error_event = {
                    'event_type': 'error',
                    'error': str(e),
                    'timestamp': asyncio.get_event_loop().time(),
                }
                yield f'data: {json.dumps(error_event)}\n\n'
            finally:
                # Clean up queue
                event_streamer.cleanup_queue(user_id, namespace, workflow_name)

        return StreamingResponse(
            generate_inference_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'text/event-stream',
                'Transfer-Encoding': 'chunked',
                'X-Accel-Buffering': 'no',  # Disable nginx buffering
            },
        )

    else:
        # Non-streaming mode - normal JSON response
        result, execution_time = await workflow_inference_service.perform_inference_v2(
            workflow_data=workflow_data,
            variables=request_body.variables or {},
            inputs=resolved_inputs
            if isinstance(resolved_inputs, list)
            else [resolved_inputs],
            output_json_enabled=request_body.output_json_enabled,
            event_callback=event_callback,
            events_filter=events_filter,
            access_token=access_token,
            app_key=app_key,
        )

        response_data = WorkflowInferenceResponse(
            result=result,
            workflow_id=workflow_name,
            namespace=namespace,
            execution_time=execution_time,
        )

        logger.info(
            f'Successfully completed v2 inference for workflow {namespace}/{workflow_name}'
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Workflow inference completed successfully',
                    'data': response_data.model_dump(),
                }
            ),
        )


@workflows_router.post('/v1/workflow-management/workflows/{name}')
@inject
async def create_workflow(
    request: Request,
    name: str = Path(..., description='The name of the workflow to create'),
    namespace: str = Query('default', description='The namespace for the workflow'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Create a new workflow

    Args:
        name: The workflow name (unique globally)
        namespace: The namespace (defaults to 'default', created if doesn't exist)
        request: Request containing raw YAML content as text/plain

    Returns:
        JSONResponse: Success or error response with workflow details
    """
    logger.info(f'Creating workflow - namespace: {namespace}, name: {name}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Read raw YAML content from request body
    yaml_content = (await request.body()).decode('utf-8')

    workflow = await workflow_crud_service.create_workflow(
        name=name,
        namespace=namespace,
        yaml_content=yaml_content,
        access_token=access_token,
        app_key=app_key,
    )

    logger.info(f'Successfully created workflow - namespace: {namespace}, name: {name}')
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow created successfully',
                'data': workflow,
            }
        ),
    )


@workflows_router.get('/v1/workflow-management/workflows/{workflow_id}')
@inject
async def get_workflow(
    workflow_id: UUID = Path(..., description='The UUID of the workflow to retrieve'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get workflow by UUID with YAML configuration

    Args:
        workflow_id: The workflow UUID

    Returns:
        JSONResponse: Workflow details including YAML content
    """
    logger.info(f'Getting workflow by ID: {workflow_id}')

    workflow = await workflow_crud_service.get_workflow(workflow_id)

    logger.info(f'Successfully retrieved workflow - ID: {workflow_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow retrieved successfully',
                'data': workflow,
            }
        ),
    )


@workflows_router.put('/v1/workflow-management/workflows/{workflow_id}')
@inject
async def update_workflow(
    request: Request,
    workflow_id: UUID = Path(..., description='The UUID of the workflow to update'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Update existing workflow YAML configuration

    Args:
        workflow_id: The workflow UUID
        request: Request containing raw YAML content as text/plain

    Returns:
        JSONResponse: Success or error response with updated workflow details
    """
    logger.info(f'Updating workflow - ID: {workflow_id}')

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Read raw YAML content from request body
    yaml_content = (await request.body()).decode('utf-8')

    workflow = await workflow_crud_service.update_workflow(
        workflow_id=workflow_id,
        yaml_content=yaml_content,
        access_token=access_token,
        app_key=app_key,
    )

    logger.info(f'Successfully updated workflow - ID: {workflow_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow updated successfully',
                'data': workflow,
            }
        ),
    )


@workflows_router.get('/v1/workflow-management/workflows')
@inject
async def list_workflows(
    namespace: str | None = Query(
        None, description='Optional namespace to filter workflows'
    ),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    List workflows with optional namespace filtering

    Args:
        namespace: Optional namespace to filter workflows (returns all if not provided)

    Returns:
        JSONResponse: List of workflows (without YAML content)
    """
    logger.info(f'Listing workflows - namespace filter: {namespace}')

    workflows_list = await workflow_crud_service.list_workflows(namespace=namespace)

    logger.info(f'Successfully retrieved {len(workflows_list)} workflows')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflows retrieved successfully',
                'data': {'workflows': workflows_list, 'count': len(workflows_list)},
            }
        ),
    )


@workflows_router.delete('/v1/workflow-management/workflows/{workflow_id}')
@inject
async def delete_workflow(
    workflow_id: UUID = Path(..., description='The UUID of the workflow to delete'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    workflow_pipeline_repository: SQLAlchemyRepository[WorkflowPipeline] = Depends(
        Provide[AgentsContainer.workflow_pipeline_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Delete a workflow by UUID

    Args:
        workflow_id: The workflow UUID

    Returns:
        JSONResponse: Success or error response
    """
    logger.info(f'Deleting workflow - ID: {workflow_id}')

    # Check if there are any workflow pipelines associated with this workflow
    workflow_pipeline = await workflow_pipeline_repository.find(workflow_id=workflow_id)

    if len(workflow_pipeline) > 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Delete workflow pipelines associated with this workflow first'
            ),
        )

    # No pipelines found, proceed with deletion
    await workflow_crud_service.delete_workflow(workflow_id)

    logger.info(f'Successfully deleted workflow - ID: {workflow_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow deleted successfully',
                'data': {'workflow_id': str(workflow_id)},
            }
        ),
    )
