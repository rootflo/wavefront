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
        conversation_config=payload.conversation_config,
        status=payload.status.value,
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

    # Parse phone_numbers from telephony config
    phone_numbers = telephony_config.get('phone_numbers')
    if (
        not phone_numbers
        or not isinstance(phone_numbers, list)
        or len(phone_numbers) == 0
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No phone numbers configured in telephony config'
            ),
        )

    # Select from_number
    from_number = payload.from_number
    if from_number:
        # Validate that provided from_number is in the configured numbers
        if from_number not in phone_numbers:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'from_number {from_number} is not in the configured phone numbers: {phone_numbers}'
                ),
            )
    else:
        # Default to first configured number
        from_number = phone_numbers[0]

    # Extract Twilio credentials from telephony config
    credentials = telephony_config.get('credentials', {})
    account_sid = credentials.get('account_sid')
    auth_token = credentials.get('auth_token')

    if not account_sid or not auth_token:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Twilio credentials (account_sid, auth_token) not found in telephony config'
            ),
        )

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

    # Initiate the call using Twilio
    call_details = twilio_service.initiate_call(
        to_number=payload.to_number,
        from_number=from_number,
        voice_agent_id=str(agent_id),
        welcome_message_audio_url=welcome_message_audio_url,
        account_sid=account_sid,
        auth_token=auth_token,
    )

    # Build response
    response_data = {
        'call_sid': call_details['call_sid'],
        'status': call_details['status'],
        'to_number': call_details['to_number'],
        'from_number': call_details['from_number'],
        'voice_agent_id': str(agent_id),
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
