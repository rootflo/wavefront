"""
Controller for message processor endpoints.
Handles creation, execution, and management of functions stored in cloud storage.
"""

from dependency_injector.wiring import inject, Provide
from fastapi import Depends, status, APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from fastapi.responses import JSONResponse
import yaml

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.message_processor_service import MessageProcessorService


message_processor_router = APIRouter()


class CreateMessageProcessorPayload(BaseModel):
    """Payload for creating a message processor from YAML."""

    name: str
    yaml_content: str  # YAML as string
    description: Optional[str] = None


class UpdateMessageProcessorPayload(BaseModel):
    """Payload for updating a message processor."""

    name: Optional[str] = None
    description: Optional[str] = None
    yaml_content: Optional[str] = None


class ExecuteMessageProcessorPayload(BaseModel):
    """Payload for executing a processor function."""

    input_data: Dict[str, Any]
    execution_context: Optional[Dict[str, Any]] = None


@message_processor_router.post('/v1/message-processors')
@inject
async def create_message_processor(
    payload: CreateMessageProcessorPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """
    Create a new message processor from YAML configuration.

    The YAML will be stored directly in the cloud storage bucket,
    and the file URL will be saved in the database.
    """
    existing_processor = await processor_service.get_message_processor(
        name=payload.name
    )
    if existing_processor:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Message processor with name {payload.name} already exists'
            ),
        )

    processor = await processor_service.create_message_processor(
        name=payload.name,
        yaml_content=payload.yaml_content,
        description=payload.description,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Message processor created successfully',
                'processor_id': str(processor.id),
            }
        ),
    )


@message_processor_router.get('/v1/message-processors')
@inject
async def list_message_processors(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """List message processors."""
    processors = await processor_service.list_message_processors()

    processors_list = [processor.to_dict() for processor in processors]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'processors': processors_list,
            }
        ),
    )


@message_processor_router.get('/v1/message-processors/{processor_id}')
@inject
async def get_message_processor(
    processor_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """Get a message processor by ID."""
    processor = await processor_service.get_message_processor(id=processor_id)

    if not processor:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Message processor {processor_id} not found'
            ),
        )

    processor_dict = processor.to_dict()

    yaml_content = await processor_service.get_message_processor_yaml_content(processor)
    processor_dict['yaml_content'] = yaml_content

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'processor': processor_dict,
            }
        ),
    )


@message_processor_router.put('/v1/message-processors/{processor_id}')
@inject
async def update_message_processor(
    processor_id: str,
    payload: UpdateMessageProcessorPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """Update a message processor."""
    processor = await processor_service.get_message_processor(id=processor_id)

    if not processor:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Message processor {processor_id} not found'
            ),
        )

    updates: Dict[str, Any] = {}
    if payload.description is not None:
        updates['description'] = payload.description

    if payload.name is not None:
        existing_processor = await processor_service.get_message_processor(
            name=payload.name
        )
        if existing_processor and str(existing_processor.id) != processor_id:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Message processor with name {payload.name} already exists'
                ),
            )
        updates['name'] = payload.name

    updated_processor = await processor_service.update_message_processor(
        processor=processor,
        updates=updates,
        yaml_content=payload.yaml_content,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'processor': updated_processor.to_dict(),
            }
        ),
    )


@message_processor_router.delete('/v1/message-processors/{processor_id}')
@inject
async def delete_message_processor(
    processor_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """Delete a message processor."""
    deleted = await processor_service.delete_message_processor(
        processor_id=processor_id
    )

    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Message processor {processor_id} not found'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f'Message processor {processor_id} deleted successfully',
            }
        ),
    )


@message_processor_router.post('/v1/message-processors/{processor_id}/execute')
@inject
async def execute_message_processor(
    processor_id: str,
    payload: ExecuteMessageProcessorPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    processor_service: MessageProcessorService = Depends(
        Provide[PluginsContainer.message_processor_service]
    ),
):
    """
    Execute a message processor function in an isolated VM.

    The function will be loaded from cloud storage and executed
    with the provided input data in the specified runtime environment.
    """
    processor = await processor_service.get_message_processor(id=processor_id)
    if not processor:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Message processor {processor_id} not found'
            ),
        )
    yaml_content = await processor_service.get_message_processor_yaml_content(processor)
    yaml_dict = yaml.safe_load(yaml_content)
    # Validate required YAML structure
    required_keys = ['function', 'input_schema', 'type']
    missing_keys = [key for key in required_keys if key not in yaml_dict]
    if missing_keys:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Invalid processor YAML: missing keys {missing_keys}'
            ),
        )

    function = yaml_dict['function']
    inputs = yaml_dict['input_schema']
    execution_environment = yaml_dict['type']
    execution_code = function['code']

    if 'required' not in inputs:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                "Invalid processor YAML: input_schema missing 'required' field"
            ),
        )

    required_inputs = inputs['required']
    execution_inputs = {}
    for input in required_inputs:
        if input not in payload.input_data.keys():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Input `{input}` is required but not provided'
                ),
            )
        execution_inputs[input] = payload.input_data[input]

    try:
        result = await processor_service.execute_message_processor(
            code=execution_code,
            type=execution_environment,
            input=execution_inputs,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'result': result,
                }
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )
