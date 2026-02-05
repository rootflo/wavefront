import json
from datetime import datetime
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.voice_agent_schemas import (
    CreateVoiceAgentPayload,
    UpdateVoiceAgentPayload,
    VoiceAgentStatus,
    UNSET,
    InitiateCallPayload,
)
from voice_agents_module.services.voice_agent_service import VoiceAgentService
from voice_agents_module.services.twilio_service import TwilioService
from voice_agents_module.services.exotel_service import ExotelService
from voice_agents_module.models.telephony_schemas import TelephonyProvider
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

voice_agent_router = APIRouter()


@voice_agent_router.post('/v1/voice-agents')
@inject
async def create_voice_agent(
    request: Request,
    payload: CreateVoiceAgentPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Create a new voice agent

    Creates a voice agent with configurations for LLM, TTS, STT, and telephony.

    Args:
        payload: Voice agent details including name, configs, and system prompt

    Returns:
        JSONResponse: Created voice agent details
    """
    agent = await voice_agent_service.create_agent(
        name=payload.name,
        description=payload.description,
        llm_config_id=payload.llm_config_id,
        tts_config_id=payload.tts_config_id,
        stt_config_id=payload.stt_config_id,
        telephony_config_id=payload.telephony_config_id,
        system_prompt=payload.system_prompt,
        welcome_message=payload.welcome_message,
        tts_voice_ids=payload.tts_voice_ids,
        tts_parameters=payload.tts_parameters,
        stt_parameters=payload.stt_parameters,
        conversation_config=payload.conversation_config,
        status=payload.status.value,
        inbound_numbers=payload.inbound_numbers,
        outbound_numbers=payload.outbound_numbers,
        supported_languages=payload.supported_languages,
        default_language=payload.default_language,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Voice agent created successfully',
                'voice_agent': agent,
            }
        ),
    )


@voice_agent_router.get('/v1/voice-agents')
@inject
async def list_voice_agents(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    List all voice agents

    Returns:
        JSONResponse: List of all voice agents
    """
    agents_data = await voice_agent_service.list_agents()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'voice_agents': agents_data}),
    )


@voice_agent_router.get('/v1/voice-agents/{agent_id}')
@inject
async def get_voice_agent(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Get a single voice agent by ID

    Args:
        agent_id: UUID of the voice agent to retrieve

    Returns:
        JSONResponse: Voice agent details
    """
    agent_dict = await voice_agent_service.get_agent(agent_id)

    if not agent_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Voice agent not found with id: {agent_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(agent_dict),
    )


@voice_agent_router.patch('/v1/voice-agents/{agent_id}')
@inject
async def update_voice_agent(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    payload: UpdateVoiceAgentPayload = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Update a voice agent

    Updates specified fields of a voice agent.
    Only provided fields will be updated.

    Args:
        agent_id: UUID of the voice agent to update
        payload: Fields to update

    Returns:
        JSONResponse: Success message
    """
    # Build update dict (only include set fields)
    update_data = {}

    if payload.name is not UNSET:
        update_data['name'] = payload.name
    if payload.description is not UNSET:
        update_data['description'] = payload.description
    if payload.llm_config_id is not UNSET:
        update_data['llm_config_id'] = payload.llm_config_id
    if payload.tts_config_id is not UNSET:
        update_data['tts_config_id'] = payload.tts_config_id
    if payload.stt_config_id is not UNSET:
        update_data['stt_config_id'] = payload.stt_config_id
    if payload.telephony_config_id is not UNSET:
        update_data['telephony_config_id'] = payload.telephony_config_id
    if payload.system_prompt is not UNSET:
        update_data['system_prompt'] = payload.system_prompt
    if payload.welcome_message is not UNSET:
        update_data['welcome_message'] = payload.welcome_message
    if payload.tts_voice_ids is not UNSET:
        update_data['tts_voice_ids'] = payload.tts_voice_ids
    if payload.tts_parameters is not UNSET:
        update_data['tts_parameters'] = payload.tts_parameters
    if payload.stt_parameters is not UNSET:
        update_data['stt_parameters'] = payload.stt_parameters
    if payload.conversation_config is not UNSET:
        update_data['conversation_config'] = (
            json.dumps(payload.conversation_config)
            if payload.conversation_config
            else None
        )
    if payload.status is not UNSET:
        if hasattr(payload.status, 'value'):
            # It's an enum object
            update_data['status'] = payload.status.value
        elif isinstance(payload.status, str) and payload.status in [
            e.value for e in VoiceAgentStatus
        ]:
            # It's a valid enum value string
            update_data['status'] = payload.status
        else:
            # Invalid value
            valid_values = [e.value for e in VoiceAgentStatus]
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid status value. Must be one of: {valid_values}'
                ),
            )
    if payload.inbound_numbers is not UNSET:
        update_data['inbound_numbers'] = payload.inbound_numbers
    if payload.outbound_numbers is not UNSET:
        update_data['outbound_numbers'] = payload.outbound_numbers
    if payload.supported_languages is not UNSET:
        update_data['supported_languages'] = payload.supported_languages
    if payload.default_language is not UNSET:
        update_data['default_language'] = payload.default_language

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    updated_agent = await voice_agent_service.update_agent(agent_id, **update_data)

    if not updated_agent:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Voice agent not found with id: {agent_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Voice agent updated successfully',
                'voice_agent': updated_agent,
            }
        ),
    )


@voice_agent_router.delete('/v1/voice-agents/{agent_id}')
@inject
async def delete_voice_agent(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Delete a voice agent (soft delete)

    Marks the voice agent as deleted (sets is_deleted=True).

    Args:
        agent_id: UUID of the voice agent to delete

    Returns:
        JSONResponse: Success message
    """
    deleted = await voice_agent_service.delete_agent(agent_id)

    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Voice agent not found with id: {agent_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Voice agent deleted successfully',
                'voice_agent_id': str(agent_id),
            }
        ),
    )


@voice_agent_router.post('/v1/voice-agents/{agent_id}/initiate')
@inject
async def initiate_call(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    payload: InitiateCallPayload = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
    twilio_service: TwilioService = Depends(
        Provide[VoiceAgentsContainer.twilio_service]
    ),
    exotel_service: ExotelService = Depends(
        Provide[VoiceAgentsContainer.exotel_service]
    ),
):
    """
    Initiate an outbound call for a voice agent

    Validates the agent, selects appropriate phone number, and initiates
    a call using Twilio.

    Args:
        agent_id: UUID of the voice agent
        payload: Call details (to_number, optional from_number)

    Returns:
        JSONResponse: Call initiation details
    """
    # Fetch the voice agent
    agent_dict = await voice_agent_service.get_agent(agent_id)

    if not agent_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Voice agent not found with id: {agent_id}'
            ),
        )

    # Check if agent is active
    if agent_dict.get('status') != 'active':
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Voice agent must be active to initiate calls. Current status: {agent_dict.get("status")}'
            ),
        )

    # Get outbound numbers from agent
    outbound_numbers = agent_dict.get('outbound_numbers', [])
    if (
        not outbound_numbers
        or not isinstance(outbound_numbers, list)
        or len(outbound_numbers) == 0
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No outbound phone numbers configured for this agent'
            ),
        )

    # Select from_number
    from_number = payload.from_number
    if from_number:
        # Validate that provided from_number is in the agent's outbound numbers
        if from_number not in outbound_numbers:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f"from_number {from_number} is not in the agent's outbound numbers: {outbound_numbers}"
                ),
            )
    else:
        # Default to first outbound number
        from_number = outbound_numbers[0]

    # Fetch telephony config
    telephony_config_id = agent_dict.get('telephony_config_id')
    telephony_config = await voice_agent_service.telephony_config_service.get_config(
        telephony_config_id
    )

    if not telephony_config:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Telephony config not found with id: {telephony_config_id}'
            ),
        )

    # Extract provider and credentials
    provider = telephony_config.get('provider')
    credentials = telephony_config.get('credentials', {})

    # Generate presigned URL for welcome message audio
    welcome_message_audio_url = ''
    if agent_dict.get('welcome_message'):
        try:
            welcome_message_audio_url = (
                await voice_agent_service.get_welcome_message_audio_url(agent_id)
            )
        except Exception as e:
            logger.error(f'Failed to generate welcome message audio URL: {str(e)}')
            # Continue with empty URL - call will proceed without welcome message

    # Route to appropriate provider service
    if provider == TelephonyProvider.TWILIO.value:
        account_sid = credentials.get('account_sid')
        auth_token = credentials.get('auth_token')

        if not account_sid or not auth_token:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    'Twilio credentials (account_sid, auth_token) missing'
                ),
            )

        call_details = twilio_service.initiate_call(
            to_number=payload.to_number,
            from_number=from_number,
            voice_agent_id=str(agent_id),
            welcome_message_audio_url=welcome_message_audio_url,
            account_sid=account_sid,
            auth_token=auth_token,
        )

    elif provider == TelephonyProvider.EXOTEL.value:
        api_key = credentials.get('api_key')
        api_token = credentials.get('api_token')
        account_sid = credentials.get('account_sid')
        subdomain = credentials.get('subdomain')

        if not all([api_key, api_token, account_sid, subdomain]):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    'Exotel credentials (api_key, api_token, account_sid, subdomain) missing'
                ),
            )

        call_details = await exotel_service.initiate_call(
            to_number=payload.to_number,
            from_number=from_number,
            voice_agent_id=str(agent_id),
            welcome_message_audio_url=welcome_message_audio_url,
            api_key=api_key,
            api_token=api_token,
            account_sid=account_sid,
            subdomain=subdomain,
        )

    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Unsupported telephony provider: {provider}'
            ),
        )

    # Build unified response
    response_data = {
        'call_sid': call_details['call_sid'],
        'status': call_details['status'],
        'to_number': call_details['to_number'],
        'from_number': call_details['from_number'],
        'voice_agent_id': str(agent_id),
        'provider': provider,
        'initiated_at': datetime.utcnow().isoformat(),
    }

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Call initiated successfully',
                'call': response_data,
            }
        ),
    )


@voice_agent_router.get('/v1/voice-agents/by-inbound-number/{phone_number}')
@inject
async def get_voice_agent_by_inbound_number(
    phone_number: str = Path(..., description='Inbound phone number (E.164 format)'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Get voice agent by inbound phone number.

    This endpoint is used by call_processing to lookup which agent handles
    a specific inbound phone number.

    Args:
        phone_number: Inbound phone number in E.164 format

    Returns:
        JSONResponse: Voice agent details or 404 if not found
    """
    agent = await voice_agent_service.get_agent_by_inbound_number(phone_number)

    if not agent:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'No voice agent found for inbound number: {phone_number}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(agent),
    )


@voice_agent_router.get('/v1/voice-agents/{agent_id}/welcome-audio-url')
@inject
async def get_welcome_audio_url(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
):
    """
    Get welcome message audio presigned URL for a voice agent.

    Returns a presigned URL (2-hour expiration) for accessing the agent's
    welcome message audio file from cloud storage.

    Args:
        agent_id: UUID of the voice agent

    Returns:
        JSONResponse: Object with 'url' field containing presigned URL
    """
    try:
        url = await voice_agent_service.get_welcome_message_audio_url(agent_id)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'url': url}),
        )

    except Exception as e:
        logger.error(f'Failed to get welcome audio URL for agent {agent_id}: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to generate welcome message URL: {str(e)}'
            ),
        )
