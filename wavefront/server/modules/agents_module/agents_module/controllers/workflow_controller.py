from typing import Optional
from uuid import UUID
from agents_module.utils.input_processing_utils import process_inference_inputs
from agents_module.utils.auth_utils import extract_auth_credentials
from fastapi import APIRouter, Depends, status, Path, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from dependency_injector.wiring import inject, Provide
import json
import asyncio
import uuid
import time

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from agents_module.utils.execution_variable_utils import with_execution_variables
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
    version: Optional[int] = Query(
        None,
        description='Specific workflow version to run; defaults to current_version',
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

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    resolved_inputs = process_inference_inputs(request_body.inputs)
    logger.info(f'Inputs to workflow: {resolved_inputs}')

    # Prepare event streaming if requested
    event_callback = None
    events_filter = None

    # Minted for every run, not only streaming ones: it is passed into the
    # workflow as a variable so nodes can stamp their outputs with the run id.
    execution_id = str(uuid.uuid4())

    if listen_events or request_body.listen_events:
        event_callback = create_workflow_event_callback(
            execution_id, namespace, workflow_id
        )
        events_filter = DEFAULT_EVENTS_FILTER
        logger.info(
            f'Event streaming enabled for execution {execution_id}, workflow {namespace}/{workflow_id}'
        )

    # Check if streaming is requested
    if listen_events or request_body.listen_events:
        logger.info(
            f'Streaming inference for execution {execution_id}, workflow {namespace}/{workflow_id}'
        )

        event_queue = event_streamer.create_queue(execution_id)

        async def generate_inference_stream():
            """Generate streaming inference with events and final output"""
            try:
                inference_task = asyncio.create_task(
                    workflow_inference_service.perform_inference(
                        workflow_name=workflow_id,
                        namespace=namespace,
                        variables=with_execution_variables(
                            request_body.variables, execution_id
                        ),
                        inputs=resolved_inputs
                        if isinstance(resolved_inputs, list)
                        else [resolved_inputs],
                        output_json_enabled=request_body.output_json_enabled,
                        event_callback=event_callback,
                        events_filter=events_filter,
                        access_token=access_token,
                        app_key=app_key,
                        version=version,
                    )
                )

                # Stream events until inference completes
                while not inference_task.done():
                    try:
                        event_data = await asyncio.wait_for(
                            event_queue.get(), timeout=1.0
                        )
                        yield f'data: {json.dumps(event_data)}\n\n'
                    except asyncio.TimeoutError:
                        continue

                # Yield to the event loop so any ensure_future(add_event(...))
                # callbacks scheduled inside the inference task have a chance
                # to run and enqueue their events before we drain.
                await asyncio.sleep(0)

                # Drain any remaining events queued after task completion
                while not event_queue.empty():
                    event_data = event_queue.get_nowait()
                    yield f'data: {json.dumps(event_data)}\n\n'

                result, execution_time = await inference_task

                output_event = {
                    'event_type': 'output',
                    'result': result,
                    'workflow_id': workflow_id,
                    'namespace': namespace,
                    'execution_time': execution_time,
                    'timestamp': time.time(),
                }
                yield f'data: {json.dumps(output_event)}\n\n'

                logger.info(
                    f'Streaming inference completed for execution {execution_id}, workflow {namespace}/{workflow_id}'
                )

            except Exception as e:
                logger.error(
                    f'Error in streaming inference for execution {execution_id}, workflow {namespace}/{workflow_id}: {e}'
                )
                error_event = {
                    'event_type': 'error',
                    'error': str(e),
                    'timestamp': time.time(),
                }
                yield f'data: {json.dumps(error_event)}\n\n'
            finally:
                event_streamer.cleanup_queue(execution_id)

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
            variables=with_execution_variables(request_body.variables, execution_id),
            inputs=resolved_inputs
            if isinstance(resolved_inputs, list)
            else [resolved_inputs],
            output_json_enabled=request_body.output_json_enabled,
            event_callback=event_callback,
            events_filter=events_filter,
            access_token=access_token,
            app_key=app_key,
            version=version,
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
    version: Optional[int] = Query(
        None,
        description='Specific workflow version to run; defaults to current_version',
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
        version: Specific workflow version to run; defaults to current_version

    Returns:
        WorkflowInferenceResponse: Contains the inference result and metadata
    """
    logger.info(
        f'Starting v2 inference for workflow_id: {workflow_id}, listen_events: {listen_events}, version: {version}'
    )
    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Fetch workflow from DB first (resolved to the requested/current version,
    # including its yaml_content, which perform_inference_v2 uses directly)
    workflow_data = await workflow_crud_service.get_workflow(
        workflow_id, version=version
    )
    namespace = workflow_data['namespace']
    workflow_name = workflow_data['name']

    resolved_inputs = process_inference_inputs(request_body.inputs)
    logger.debug(f'Inputs to workflow: {resolved_inputs}')

    # Prepare event streaming if requested
    event_callback = None
    events_filter = None

    # Minted for every run, not only streaming ones: it is passed into the
    # workflow as a variable so nodes can stamp their outputs with the run id.
    execution_id = str(uuid.uuid4())

    if listen_events or request_body.listen_events:
        event_callback = create_workflow_event_callback(
            execution_id, namespace, workflow_name
        )
        events_filter = DEFAULT_EVENTS_FILTER
        logger.info(
            f'Event streaming enabled for execution {execution_id}, workflow {namespace}/{workflow_name}'
        )

    # Check if streaming is requested
    if listen_events or request_body.listen_events:
        logger.info(
            f'Streaming inference for execution {execution_id}, workflow {namespace}/{workflow_name}'
        )

        event_queue = event_streamer.create_queue(execution_id)

        async def generate_inference_stream():
            """Generate streaming inference with events and final output"""
            try:
                inference_task = asyncio.create_task(
                    workflow_inference_service.perform_inference_v2(
                        workflow_data=workflow_data,
                        variables=with_execution_variables(
                            request_body.variables, execution_id
                        ),
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

                # Stream events until inference completes
                while not inference_task.done():
                    try:
                        event_data = await asyncio.wait_for(
                            event_queue.get(), timeout=1.0
                        )
                        yield f'data: {json.dumps(event_data)}\n\n'
                    except asyncio.TimeoutError:
                        continue

                # Yield to the event loop so any ensure_future(add_event(...))
                # callbacks scheduled inside the inference task have a chance
                # to run and enqueue their events before we drain.
                await asyncio.sleep(0)

                # Drain any remaining events queued after task completion
                while not event_queue.empty():
                    event_data = event_queue.get_nowait()
                    yield f'data: {json.dumps(event_data)}\n\n'

                result, execution_time, _trace = await inference_task

                output_event = {
                    'event_type': 'output',
                    'result': result,
                    'workflow_id': workflow_name,
                    'namespace': namespace,
                    'execution_time': execution_time,
                    'timestamp': time.time(),
                }
                yield f'data: {json.dumps(output_event)}\n\n'

                logger.info(
                    f'Streaming inference completed for execution {execution_id}, workflow {namespace}/{workflow_name}'
                )

            except Exception as e:
                logger.error(
                    f'Error in streaming inference for execution {execution_id}: {e}'
                )
                error_event = {
                    'event_type': 'error',
                    'error': str(e),
                    'timestamp': time.time(),
                }
                yield f'data: {json.dumps(error_event)}\n\n'
            finally:
                event_streamer.cleanup_queue(execution_id)

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
        (
            result,
            execution_time,
            _trace,
        ) = await workflow_inference_service.perform_inference_v2(
            workflow_data=workflow_data,
            variables=with_execution_variables(request_body.variables, execution_id),
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
    version: Optional[int] = Query(
        None, description='Specific version to fetch; defaults to current_version'
    ),
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
        version: Specific version to fetch; defaults to current_version

    Returns:
        JSONResponse: Workflow details including YAML content
    """
    logger.info(f'Getting workflow by ID: {workflow_id}, version: {version}')

    workflow = await workflow_crud_service.get_workflow(workflow_id, version=version)

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


@workflows_router.get('/v1/workflow-management/workflows/{workflow_id}/versions')
@inject
async def list_workflow_versions(
    workflow_id: UUID = Path(..., description='The UUID of the workflow'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    List every live version of a workflow

    Args:
        workflow_id: The workflow UUID

    Returns:
        JSONResponse: List of versions, each annotated with is_current
    """
    logger.info(f'Listing versions for workflow - ID: {workflow_id}')

    versions = await workflow_crud_service.list_workflow_versions(workflow_id)

    logger.info(
        f'Successfully retrieved {len(versions)} versions for workflow - ID: {workflow_id}'
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow versions retrieved successfully',
                'data': {'versions': versions, 'count': len(versions)},
            }
        ),
    )


@workflows_router.patch(
    '/v1/workflow-management/workflows/{workflow_id}/current-version'
)
@inject
async def promote_workflow_version(
    workflow_id: UUID = Path(..., description='The UUID of the workflow'),
    version: int = Query(..., description='The version to promote to current_version'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Promote an existing version to be the workflow's current_version

    Args:
        workflow_id: The workflow UUID
        version: The version to promote

    Returns:
        JSONResponse: Updated workflow details
    """
    logger.info(f'Promoting workflow {workflow_id} to version {version}')

    workflow = await workflow_crud_service.promote_workflow_version(
        workflow_id, version
    )

    logger.info(f'Successfully promoted workflow {workflow_id} to version {version}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow version promoted successfully',
                'data': workflow,
            }
        ),
    )


@workflows_router.delete(
    '/v1/workflow-management/workflows/{workflow_id}/versions/{version}'
)
@inject
async def delete_workflow_version(
    workflow_id: UUID = Path(..., description='The UUID of the workflow'),
    version: int = Path(..., description='The version to delete'),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Delete a single version of a workflow (soft delete; version numbers are never reused)

    Args:
        workflow_id: The workflow UUID
        version: The version to delete

    Returns:
        JSONResponse: Success response

    Raises:
        Rejected if `version` is the workflow's current_version
    """
    logger.info(f'Deleting workflow {workflow_id} version {version}')

    await workflow_crud_service.delete_workflow_version(workflow_id, version)

    logger.info(f'Successfully deleted workflow {workflow_id} version {version}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Workflow version deleted successfully',
                'data': {'workflow_id': str(workflow_id), 'version': version},
            }
        ),
    )


@workflows_router.put('/v1/workflow-management/workflows/{workflow_id}')
@inject
async def update_workflow(
    request: Request,
    workflow_id: UUID = Path(..., description='The UUID of the workflow to update'),
    version: Optional[int] = Query(
        None,
        description='Which existing version to edit/branch from; defaults to current_version',
    ),
    create_new_version: bool = Query(
        False, description='If true, create a new version instead of editing in place'
    ),
    workflow_crud_service: WorkflowCrudService = Depends(
        Provide[AgentsContainer.workflow_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Update existing workflow YAML configuration - in place, or as a new version

    Args:
        workflow_id: The workflow UUID
        request: Request containing raw YAML content as text/plain
        version: Which existing version to edit/branch from; defaults to current_version
        create_new_version: If true, create a new version instead of editing in place

    Returns:
        JSONResponse: Success or error response with updated workflow details
    """
    logger.info(
        f'Updating workflow - ID: {workflow_id}, version: {version}, create_new_version: {create_new_version}'
    )

    # Extract authentication credentials
    access_token, app_key = extract_auth_credentials(request)

    # Read raw YAML content from request body
    yaml_content = (await request.body()).decode('utf-8')

    workflow = await workflow_crud_service.update_workflow(
        workflow_id=workflow_id,
        yaml_content=yaml_content,
        access_token=access_token,
        app_key=app_key,
        version=version,
        create_new_version=create_new_version,
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
