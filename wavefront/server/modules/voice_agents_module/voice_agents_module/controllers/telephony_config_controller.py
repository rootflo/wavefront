import json
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.telephony_schemas import (
    CreateTelephonyConfigPayload,
    UpdateTelephonyConfigPayload,
    TelephonyProvider,
    ConnectionType,
    UNSET,
)
from voice_agents_module.services.telephony_config_service import TelephonyConfigService
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

telephony_config_router = APIRouter()


@telephony_config_router.post('/v1/telephony-configs')
@inject
async def create_telephony_config(
    request: Request,
    payload: CreateTelephonyConfigPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    telephony_config_service: TelephonyConfigService = Depends(
        Provide[VoiceAgentsContainer.telephony_config_service]
    ),
):
    """
    Create a new telephony configuration

    Creates a telephony provider configuration (Twilio) with connection settings.
    For WebSocket connections, webhook_config with status_callback_url is required.
    For SIP connections, sip_config with sip_domain is required.

    Args:
        payload: Configuration details including provider, connection_type, credentials, etc.

    Returns:
        JSONResponse: Created configuration (credentials excluded)
    """
    config = await telephony_config_service.create_config(
        display_name=payload.display_name,
        description=payload.description,
        provider=payload.provider.value,
        connection_type=payload.connection_type.value,
        credentials=payload.credentials,
        webhook_config=payload.webhook_config,
        sip_config=payload.sip_config,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Telephony configuration created successfully',
                'telephony_config_id': str(config['id']),
            }
        ),
    )


@telephony_config_router.get('/v1/telephony-configs')
@inject
async def list_telephony_configs(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    telephony_config_service: TelephonyConfigService = Depends(
        Provide[VoiceAgentsContainer.telephony_config_service]
    ),
):
    """
    List all telephony configurations

    Returns:
        JSONResponse: List of configurations (credentials excluded)
    """
    configs_data = await telephony_config_service.list_configs()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'telephony_configs': configs_data}
        ),
    )


@telephony_config_router.get('/v1/telephony-configs/{config_id}')
@inject
async def get_telephony_config(
    config_id: UUID = Path(..., description='The ID of the telephony configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    telephony_config_service: TelephonyConfigService = Depends(
        Provide[VoiceAgentsContainer.telephony_config_service]
    ),
):
    """
    Get a single telephony configuration by ID

    Args:
        config_id: UUID of the configuration to retrieve

    Returns:
        JSONResponse: Configuration details (credentials excluded)
    """
    config_dict = await telephony_config_service.get_config(config_id)

    if not config_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Telephony configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(config_dict),
    )


@telephony_config_router.put('/v1/telephony-configs/{config_id}')
@inject
async def update_telephony_config(
    config_id: UUID = Path(..., description='The ID of the telephony configuration'),
    payload: UpdateTelephonyConfigPayload = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    telephony_config_service: TelephonyConfigService = Depends(
        Provide[VoiceAgentsContainer.telephony_config_service]
    ),
):
    """
    Update a telephony configuration

    Updates specified fields of a telephony configuration.
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
            e.value for e in TelephonyProvider
        ]:
            # It's a valid enum value string
            update_data['provider'] = payload.provider
        else:
            # Invalid value
            valid_values = [e.value for e in TelephonyProvider]
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid provider value. Must be one of: {valid_values}'
                ),
            )
    if payload.connection_type is not UNSET:
        if hasattr(payload.connection_type, 'value'):
            # It's an enum object
            update_data['connection_type'] = payload.connection_type.value
        elif isinstance(payload.connection_type, str) and payload.connection_type in [
            e.value for e in ConnectionType
        ]:
            # It's a valid enum value string
            update_data['connection_type'] = payload.connection_type
        else:
            # Invalid value
            valid_values = [e.value for e in ConnectionType]
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid connection_type value. Must be one of: {valid_values}'
                ),
            )
    if payload.credentials is not UNSET:
        update_data['credentials'] = json.dumps(payload.credentials)
    if payload.webhook_config is not UNSET:
        update_data['webhook_config'] = (
            json.dumps(payload.webhook_config.model_dump())
            if payload.webhook_config
            else None
        )
    if payload.sip_config is not UNSET:
        update_data['sip_config'] = (
            json.dumps(payload.sip_config.model_dump()) if payload.sip_config else None
        )

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    updated_config = await telephony_config_service.update_config(
        config_id, **update_data
    )

    if not updated_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Telephony configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Telephony configuration updated successfully',
                'telephony_config_id': str(config_id),
            }
        ),
    )


@telephony_config_router.delete('/v1/telephony-configs/{config_id}')
@inject
async def delete_telephony_config(
    config_id: UUID = Path(..., description='The ID of the telephony configuration'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    telephony_config_service: TelephonyConfigService = Depends(
        Provide[VoiceAgentsContainer.telephony_config_service]
    ),
):
    """
    Delete a telephony configuration (soft delete)

    Marks the configuration as deleted (sets is_deleted=True).

    Args:
        config_id: UUID of the configuration to delete

    Returns:
        JSONResponse: Success message
    """
    deleted = await telephony_config_service.delete_config(config_id)

    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Telephony configuration not found with id: {config_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Telephony configuration deleted successfully',
                'telephony_config_id': str(config_id),
            }
        ),
    )
