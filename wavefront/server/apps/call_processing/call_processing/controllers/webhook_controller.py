"""
Telephony webhook endpoints

TwiML generation for Twilio and the media stream WebSockets of every telephony
provider (the calls themselves are handled by ``TelephonySessionService``).
"""

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, WebSocket, Query, Depends, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from call_processing.di.application_container import ApplicationContainer
from call_processing.log.logger import logger
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from call_processing.services.telephony.session_service import (
    TelephonySessionService,
)

webhook_router = APIRouter()


def _media_stream_websocket_url(base_url: str | None) -> str:
    """Build the Twilio Media Stream wss URL from the call-processing base URL."""
    resolved = base_url or 'http://localhost:8004'
    if resolved.startswith('https://'):
        websocket_url = resolved.replace('https://', 'wss://')
    elif resolved.startswith('http://'):
        websocket_url = resolved.replace('http://', 'wss://')
    else:
        websocket_url = f'wss://{resolved}'
    return f'{websocket_url}/webhooks/ws'


def _stream_twiml(
    base_url: str | None, voice_agent_id: str, customer_number: str, agent_number: str
) -> Response:
    """TwiML that connects the call to our media stream WebSocket."""
    websocket_url = _media_stream_websocket_url(base_url)
    logger.info(f'WebSocket URL: {websocket_url}')

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=websocket_url)

    # Pass parameters to WebSocket stream
    stream.parameter(name='voice_agent_id', value=voice_agent_id)
    stream.parameter(name='customer_number', value=customer_number)
    stream.parameter(name='agent_number', value=agent_number)

    connect.append(stream)
    response.append(connect)

    # Pause for 60 seconds before auto-hangup (adjust as needed)
    response.pause(length=60)

    twiml_xml = str(response)
    logger.debug(f'Returning TwiML: {twiml_xml}')
    return Response(content=twiml_xml, media_type='application/xml')


@webhook_router.post('/inbound')
@inject
async def inbound_webhook(
    From: str = Form(...),
    To: str = Form(...),
    CallSid: str = Form(...),
    voice_agent_cache_service: VoiceAgentCacheService = Depends(
        Provide[ApplicationContainer.voice_agent_cache_service]
    ),
    call_processing_base_url: str = Depends(
        Provide[ApplicationContainer.config.env_config.call_processing_base_url]
    ),
):
    """
    Twilio inbound webhook endpoint

    Called by Twilio when an inbound call is received.
    Looks up the voice agent by inbound phone number and redirects to TwiML endpoint.

    Form params (from Twilio):
        From: Caller's phone number (E.164 format)
        To: Called phone number (E.164 format, the inbound number)
        CallSid: Twilio call identifier
    """
    # Mask phone numbers for privacy (show last 4 digits only)
    masked_from = f'***{From[-4:]}' if len(From) > 4 else '****'
    masked_to = f'***{To[-4:]}' if len(To) > 4 else '****'
    logger.info(
        f'Inbound call received: From={masked_from}, To={masked_to}, CallSid={CallSid}'
    )

    # Look up agent by inbound number
    agent = await voice_agent_cache_service.get_agent_by_inbound_number(To)

    if not agent:
        logger.error(f'No voice agent found for inbound number: {To}')
        # Return TwiML with error message
        response = VoiceResponse()
        response.say('Sorry, this number is not configured for voice services.')
        response.hangup()
        return Response(content=str(response), media_type='application/xml')

    agent_id = agent['id']
    logger.info(f'Agent found for inbound number {To}: {agent_id} ({agent["name"]})')

    return _stream_twiml(
        call_processing_base_url,
        voice_agent_id=agent_id,
        customer_number=From,
        agent_number=To,
    )


@webhook_router.post('/twiml')
@inject
async def twiml_endpoint(
    From: str = Form(...),
    To: str = Form(...),
    voice_agent_id: str = Query(...),
    call_processing_base_url: str = Depends(
        Provide[ApplicationContainer.config.env_config.call_processing_base_url]
    ),
):
    """
    Twilio TwiML endpoint

    Called by Twilio when call connects (directly or via outbound webhook redirect).
    Returns TwiML XML with WebSocket connection instructions.

    Query params:
        voice_agent_id: UUID of the voice agent configuration
    """
    logger.info(f'TwiML requested for voice_agent_id: {voice_agent_id}')

    return _stream_twiml(
        call_processing_base_url,
        voice_agent_id=voice_agent_id,
        customer_number=To,
        agent_number=From,
    )


@webhook_router.websocket('/ws')
@inject
async def websocket_endpoint(
    websocket: WebSocket,
    telephony_session_service: TelephonySessionService = Depends(
        Provide[ApplicationContainer.telephony_session_service]
    ),
):
    """
    Media Stream WebSocket endpoint (Twilio / Exotel / Smartflo)

    Handles bidirectional audio streaming with Pipecat pipeline.
    """
    await websocket.accept()
    logger.info('WebSocket connection accepted')
    await telephony_session_service.handle_stream(websocket)


@webhook_router.websocket('/exotel/inbound/ws')
@inject
async def exotel_inbound_websocket(
    websocket: WebSocket,
    telephony_session_service: TelephonySessionService = Depends(
        Provide[ApplicationContainer.telephony_session_service]
    ),
):
    """
    Exotel inbound WebSocket endpoint

    Direct WebSocket connection for Exotel AppBazaar voicebot integration.
    Handles bidirectional audio streaming with Pipecat pipeline.

    Parameters are extracted from the Exotel WebSocket stream:
        CallSid: Exotel call identifier
        From: Caller's phone number (E.164 format)
        To: Called phone number (for agent lookup)
    """
    await websocket.accept()
    logger.info('Exotel WebSocket connection accepted')
    await telephony_session_service.handle_exotel_inbound(websocket)
