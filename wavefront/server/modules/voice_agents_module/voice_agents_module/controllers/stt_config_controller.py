from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.stt_schemas import (
    CreateSttConfigPayload,
    UpdateSttConfigPayload,
    UNSET,
)
from voice_agents_module.services.stt_config_service import SttConfigService
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

stt_config_router = APIRouter()


@stt_config_router.post('/v1/stt-configs')
@inject
async def create_stt_config(
    request: Request,
    payload: CreateSttConfigPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    stt_config_service: SttConfigService = Depends(
        Provide[VoiceAgentsContainer.stt_config_service]
    ),
):
    """
    Create a new STT configuration

    Creates a Speech-to-Text provider configuration with credentials only.

    Args:
        payload: Configuration details including provider and api_key

    Returns:
        JSONResponse: Created configuration (api_key excluded)
    """
    config = await stt_config_service.create_config(
        display_name=payload.display_name,
        description=payload.description,
        provider=payload.provider.value,
        api_key=payload.api_key,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'STT configuration created successfully',
                'stt_config_id': str(config['id']),
            }
        ),
    )


@stt_config_router.get('/v1/stt-configs')
@inject
async def list_stt_configs(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    stt_config_service: SttConfigService = Depends(
        Provide[VoiceAgentsContainer.stt_config_service]
    ),
):
    """
    List all STT configurations

    Returns:
        JSONResponse: List of configurations (api_key excluded)
    """
    configs_data = await stt_config_service.list_configs()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'stt_configs': configs_data}),
    )


@stt_config_router.get('/v1/stt-configs/{config_id}')
@inject
async def get_stt_config(
    config_id: UUID = Path(..., description='The ID of the STT configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    stt_config_service: SttConfigService = Depends(
        Provide[VoiceAgentsContainer.stt_config_service]
    ),
):
    """
    Get a single STT configuration by ID

    Args:
        config_id: UUID of the configuration to retrieve

    Returns:
        JSONResponse: Configuration details (api_key excluded)
    """
    config_dict = await stt_config_service.get_config(config_id)

    if not config_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'STT configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(config_dict),
    )


@stt_config_router.put('/v1/stt-configs/{config_id}')
@inject
async def update_stt_config(
    config_id: UUID = Path(..., description='The ID of the STT configuration'),
    payload: UpdateSttConfigPayload = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    stt_config_service: SttConfigService = Depends(
        Provide[VoiceAgentsContainer.stt_config_service]
    ),
):
    """
    Update an STT configuration

    Updates specified fields of an STT configuration.
    Only provided fields will be updated.

    Args:
        config_id: UUID of the configuration to update
        payload: Fields to update

    Returns:
        JSONResponse: Success message
    """
    # Build update dict (only include set fields)
    update_data = {}
    if payload.display_name is not UNSET:
        update_data['display_name'] = payload.display_name
    if payload.description is not UNSET:
        update_data['description'] = payload.description
    if payload.api_key is not UNSET:
        update_data['api_key'] = payload.api_key

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    updated_config = await stt_config_service.update_config(config_id, **update_data)

    if not updated_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'STT configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'STT configuration updated successfully',
                'stt_config_id': str(config_id),
            }
        ),
    )


@stt_config_router.delete('/v1/stt-configs/{config_id}')
@inject
async def delete_stt_config(
    config_id: UUID = Path(..., description='The ID of the STT configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    stt_config_service: SttConfigService = Depends(
        Provide[VoiceAgentsContainer.stt_config_service]
    ),
):
    """
    Delete an STT configuration (soft delete)

    Marks the configuration as deleted (sets is_deleted=True).

    Args:
        config_id: UUID of the configuration to delete

    Returns:
        JSONResponse: Success message
    """
    deleted = await stt_config_service.delete_config(config_id)

    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'STT configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'STT configuration deleted successfully',
                'stt_config_id': str(config_id),
            }
        ),
    )
