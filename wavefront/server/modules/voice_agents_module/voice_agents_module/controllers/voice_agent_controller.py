import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Path, Request, status
from fastapi.responses import JSONResponse, Response

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.voice_agent_schemas import (
    CreateVoiceAgentPayload,
    CreateWebRTCRoomPayload,
    UpdateVoiceAgentPayload,
    VoiceAgentStatus,
    UNSET,
    InitiateCallPayload,
)
from voice_agents_module.services.voice_agent_service import VoiceAgentService
from voice_agents_module.services.twilio_service import TwilioService
from voice_agents_module.services.exotel_service import ExotelService
from voice_agents_module.services.smartflo_service import SmartfloService
from voice_agents_module.services.webrtc_room_client import (
    WebRTCRoomClient,
    WebRTCRoomClientError,
)
from voice_agents_module.models.telephony_schemas import TelephonyProvider
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

voice_agent_router = APIRouter()

# Upper bound on agents a browser room may switch between
MAX_ROOM_SWITCHABLE_AGENTS = 20


def _room_agent_choices(
    initial_agent: Dict[str, Any],
    all_agents: List[Dict[str, Any]],
    narrow_to: Optional[List[UUID]],
) -> List[Dict[str, str]]:
    """The agents a browser room may hot-swap between, initial agent first.

    Only active, non-deleted agents qualify. ``narrow_to`` (from the caller)
    can only shrink the set, never add to it.
    """
    initial_id = str(initial_agent['id'])
    wanted = {str(a) for a in narrow_to} if narrow_to is not None else None

    choices = [{'id': initial_id, 'name': initial_agent.get('name') or ''}]
    seen = {initial_id}
    for agent in all_agents:
        agent_id = str(agent.get('id'))
        if agent_id in seen:
            continue
        if agent.get('status') != 'active' or agent.get('is_deleted'):
            continue
        if wanted is not None and agent_id not in wanted:
            continue
        seen.add(agent_id)
        choices.append({'id': agent_id, 'name': agent.get('name') or ''})
        if len(choices) >= MAX_ROOM_SWITCHABLE_AGENTS:
            break
    return choices


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
        welcome_message=payload.welcome_message or '',
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
    List voice agents (table/summary fields only).

    Omits prompts, TTS/STT parameters, and config IDs. Use
    ``GET /v1/voice-agents/{agent_id}`` (or ``.../details``) for the full
    agent payload needed by edit and operations flows.
    """
    agents_data = await voice_agent_service.list_agents()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'voice_agents': agents_data}),
    )


@voice_agent_router.get('/v1/voice-agents/{agent_id}')
@voice_agent_router.get('/v1/voice-agents/{agent_id}/details')
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
    Get full details for a single voice agent.

    Includes prompts, config IDs, TTS/STT parameters, and conversation config.
    Prefer this over the list endpoint before edit or call operations.
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
    smartflo_service: SmartfloService = Depends(
        Provide[VoiceAgentsContainer.smartflo_service]
    ),
):
    """
    Initiate an outbound call for a voice agent

    Validates the agent, selects appropriate phone number, and initiates
    a call using the configured telephony provider.

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
                f"Voice agent must be active to initiate calls. Current status: {agent_dict.get('status')}"
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

    # Fetch telephony config with plaintext credentials
    telephony_config_id = agent_dict.get('telephony_config_id')
    telephony_config = (
        await voice_agent_service.telephony_config_service.get_runtime_config(
            telephony_config_id
        )
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
            api_key=api_key,
            api_token=api_token,
            account_sid=account_sid,
            subdomain=subdomain,
        )

    elif provider == TelephonyProvider.SMARTFLO.value:
        api_key = credentials.get('api_key')

        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    'Smartflo credentials (api_key) missing'
                ),
            )

        call_details = await smartflo_service.initiate_call(
            to_number=payload.to_number,
            from_number=from_number,
            voice_agent_id=str(agent_id),
            api_key=api_key,
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


@voice_agent_router.post(
    '/v1/voice-agents/{agent_id}/rooms', status_code=status.HTTP_201_CREATED
)
@inject
async def create_webrtc_room(
    agent_id: UUID = Path(..., description='The ID of the voice agent'),
    payload: Optional[CreateWebRTCRoomPayload] = Body(default=None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    voice_agent_service: VoiceAgentService = Depends(
        Provide[VoiceAgentsContainer.voice_agent_service]
    ),
    webrtc_room_client: WebRTCRoomClient = Depends(
        Provide[VoiceAgentsContainer.webrtc_room_client]
    ),
):
    """
    Create a browser (WebRTC) voice room for an active voice agent.

    Returns ``room_id``, ``voice_agent_id``, a one-time ``join_token`` (shown
    once; the browser sends it with its SDP offer) and the ``signaling_url``
    the browser should use. No outbound phone numbers are required.

    The room can hot-swap to the other *active* agents: their ids are stored on
    the room as an allowlist (the browser cannot add to it). The optional body
    ``allowed_agent_ids`` narrows it. ``agents`` lists ``{id, name}`` of every
    agent the room can run (the initial one first) for the client's picker.

    ``room_context_handles_language`` (default false): when true the app drives
    the language through ``set_context.language``, so the agent is built without
    the language-switching rules and ``detect_and_switch_language`` tool.

    ``carry_history_on_swap`` (default true): when the room switches agents the
    new agent inherits the conversation so far. False starts it with a clean
    context.
    """
    agent_dict = await voice_agent_service.get_agent(agent_id)

    if not agent_dict:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Voice agent not found with id: {agent_id}'
            ),
        )

    if agent_dict.get('status') != 'active':
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f"Voice agent must be active to start a browser call. Current status: {agent_dict.get('status')}"
            ),
        )

    all_agents = await voice_agent_service.list_agents()
    agents = _room_agent_choices(
        agent_dict, all_agents, payload.allowed_agent_ids if payload else None
    )

    try:
        room = await webrtc_room_client.create_room(
            agent_id,
            allowed_agent_ids=[UUID(a['id']) for a in agents],
            room_context_handles_language=bool(
                payload and payload.room_context_handles_language
            ),
            carry_history_on_swap=payload.carry_history_on_swap if payload else True,
        )
    except WebRTCRoomClientError as e:
        return JSONResponse(
            status_code=e.status_code,
            content=response_formatter.buildErrorResponse(e.message),
        )

    room['agents'] = agents
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(room),
    )


async def _proxy_webrtc_signaling(
    method: str,
    request: Request,
    response_formatter: ResponseFormatter,
    webrtc_room_client: WebRTCRoomClient,
) -> Response:
    try:
        proxied = await webrtc_room_client.forward_signaling(
            method, await request.body(), request.headers.get('cookie')
        )
    except WebRTCRoomClientError as e:
        return JSONResponse(
            status_code=e.status_code,
            content=response_formatter.buildErrorResponse(e.message),
        )

    response = Response(
        content=proxied.content,
        status_code=proxied.status_code,
        media_type=proxied.media_type,
    )
    if proxied.set_cookie:
        response.headers['set-cookie'] = proxied.set_cookie
    return response


@voice_agent_router.post('/v1/webrtc/offer')
@inject
async def proxy_webrtc_offer(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    webrtc_room_client: WebRTCRoomClient = Depends(
        Provide[VoiceAgentsContainer.webrtc_room_client]
    ),
):
    """SDP offer proxy to call_processing (only when signaling via floware is enabled)."""
    return await _proxy_webrtc_signaling(
        'POST', request, response_formatter, webrtc_room_client
    )


@voice_agent_router.patch('/v1/webrtc/offer')
@inject
async def proxy_webrtc_ice_candidates(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    webrtc_room_client: WebRTCRoomClient = Depends(
        Provide[VoiceAgentsContainer.webrtc_room_client]
    ),
):
    """Trickle ICE proxy to call_processing (only when signaling via floware is enabled)."""
    return await _proxy_webrtc_signaling(
        'PATCH', request, response_formatter, webrtc_room_client
    )
