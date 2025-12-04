import json
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.tts_schemas import (
    CreateTtsConfigPayload,
    UpdateTtsConfigPayload,
    TtsProvider,
    UNSET,
)
from voice_agents_module.services.tts_config_service import TtsConfigService
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

tts_config_router = APIRouter()


@tts_config_router.post('/v1/tts-configs')
@inject
async def create_tts_config(
    request: Request,
    payload: CreateTtsConfigPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tts_config_service: TtsConfigService = Depends(
        Provide[VoiceAgentsContainer.tts_config_service]
    ),
):
    """
    Create a new TTS configuration

    Creates a Text-to-Speech provider configuration with voice settings.

    Args:
        payload: Configuration details including provider, voice_id, api_key, etc.

    Returns:
        JSONResponse: Created configuration (api_key excluded)
    """
    config = await tts_config_service.create_config(
        display_name=payload.display_name,
        description=payload.description,
        provider=payload.provider.value,
        voice_id=payload.voice_id,
        api_key=payload.api_key,
        language=payload.language,
        parameters=payload.parameters,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'TTS configuration created successfully',
                'tts_config_id': str(config['id']),
            }
        ),
    )


@tts_config_router.get('/v1/tts-configs')
@inject
async def list_tts_configs(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tts_config_service: TtsConfigService = Depends(
        Provide[VoiceAgentsContainer.tts_config_service]
    ),
):
    """
    List all TTS configurations

    Returns:
        JSONResponse: List of configurations (api_key excluded)
    """
    configs_data = await tts_config_service.list_configs()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'tts_configs': configs_data}),
    )


@tts_config_router.get('/v1/tts-configs/{config_id}')
@inject
async def get_tts_config(
    config_id: UUID = Path(..., description='The ID of the TTS configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tts_config_service: TtsConfigService = Depends(
        Provide[VoiceAgentsContainer.tts_config_service]
    ),
):
    """
    Get a single TTS configuration by ID

    Args:
        config_id: UUID of the configuration to retrieve

    Returns:
        JSONResponse: Configuration details (api_key excluded)
    """
    config_dict = await tts_config_service.get_config(config_id)

    if not config_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'TTS configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(config_dict),
    )


@tts_config_router.put('/v1/tts-configs/{config_id}')
@inject
async def update_tts_config(
    config_id: UUID = Path(..., description='The ID of the TTS configuration'),
    payload: UpdateTtsConfigPayload = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tts_config_service: TtsConfigService = Depends(
        Provide[VoiceAgentsContainer.tts_config_service]
    ),
):
    """
    Update a TTS configuration

    Updates specified fields of a TTS configuration.
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
    if payload.provider is not UNSET:
        if hasattr(payload.provider, 'value'):
            # It's an enum object
            update_data['provider'] = payload.provider.value
        elif isinstance(payload.provider, str) and payload.provider in [
            e.value for e in TtsProvider
        ]:
            # It's a valid enum value string
            update_data['provider'] = payload.provider
        else:
            # Invalid value
            valid_values = [e.value for e in TtsProvider]
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid provider value. Must be one of: {valid_values}'
                ),
            )
    if payload.voice_id is not UNSET:
        update_data['voice_id'] = payload.voice_id
    if payload.api_key is not UNSET:
        update_data['api_key'] = payload.api_key
    if payload.language is not UNSET:
        update_data['language'] = payload.language
    if payload.parameters is not UNSET:
        update_data['parameters'] = (
            json.dumps(payload.parameters) if payload.parameters else None
        )

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    updated_config = await tts_config_service.update_config(config_id, **update_data)

    if not updated_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'TTS configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'TTS configuration updated successfully',
                'tts_config_id': str(config_id),
            }
        ),
    )


@tts_config_router.delete('/v1/tts-configs/{config_id}')
@inject
async def delete_tts_config(
    config_id: UUID = Path(..., description='The ID of the TTS configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tts_config_service: TtsConfigService = Depends(
        Provide[VoiceAgentsContainer.tts_config_service]
    ),
):
    """
    Delete a TTS configuration (soft delete)

    Marks the configuration as deleted (sets is_deleted=True).

    Args:
        config_id: UUID of the configuration to delete

    Returns:
        JSONResponse: Success message
    """
    deleted = await tts_config_service.delete_config(config_id)

    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'TTS configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'TTS configuration deleted successfully',
                'tts_config_id': str(config_id),
            }
        ),
    )
