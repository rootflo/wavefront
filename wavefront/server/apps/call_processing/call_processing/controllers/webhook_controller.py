"""
Twilio webhook endpoints

Handles TwiML generation and WebSocket audio streaming
"""

import os
from uuid import UUID
from fastapi import APIRouter, WebSocket, Query, Depends, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from call_processing.log.logger import logger
from dependency_injector.wiring import inject, Provide

# Pipecat imports for WebSocket handling
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.runner.utils import parse_telephony_websocket

from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)

from call_processing.services.voice_agent_cache_service import VoiceAgentCacheService
from call_processing.services.pipecat_service import PipecatService
from call_processing.di.application_container import ApplicationContainer

webhook_router = APIRouter()


@webhook_router.post('/inbound')
@inject
async def inbound_webhook(
    From: str = Form(...),
    To: str = Form(...),
    CallSid: str = Form(...),
    voice_agent_cache_service: VoiceAgentCacheService = Depends(
        Provide[ApplicationContainer.voice_agent_cache_service]
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

    # Generate welcome message audio URL
    welcome_message_audio_url = ''
    if agent.get('welcome_message'):
        try:
            # Note: This assumes voice_agent_cache_service has this method
            # We'll implement it in the next step
            welcome_message_audio_url = (
                await voice_agent_cache_service.get_welcome_message_audio_url(agent_id)
            )
        except Exception as e:
            logger.error(f'Failed to get welcome message URL: {e}')
            # Continue without welcome message

    # Build WebSocket URL
    base_url = os.getenv('CALL_PROCESSING_BASE_URL', 'http://localhost:8003')

    # Convert https:// to wss:// (or http:// to ws://)
    if base_url.startswith('https://'):
        websocket_url = base_url.replace('https://', 'wss://')
    elif base_url.startswith('http://'):
        websocket_url = base_url.replace('http://', 'ws://')
    else:
        websocket_url = f'wss://{base_url}'

    websocket_url = f'{websocket_url}/webhooks/ws'

    logger.info(f'WebSocket URL: {websocket_url}')

    # Generate TwiML response
    response = VoiceResponse()

    # Play welcome message audio if URL is provided
    if welcome_message_audio_url:
        response.play(welcome_message_audio_url)
    else:
        logger.warning(
            'No welcome message audio URL provided, skipping welcome message'
        )

    connect = Connect()
    stream = Stream(url=websocket_url)

    # Pass parameters to WebSocket stream
    stream.parameter(name='voice_agent_id', value=agent_id)
    stream.parameter(name='customer_number', value=From)
    stream.parameter(name='agent_number', value=To)

    connect.append(stream)
    response.append(connect)

    # Pause for 60 seconds before auto-hangup (adjust as needed)
    response.pause(length=60)

    twiml_xml = str(response)
    logger.info(f'Returning TwiML: {twiml_xml}')

    return Response(content=twiml_xml, media_type='application/xml')


@webhook_router.post('/twiml')
async def twiml_endpoint(
    From: str = Form(...),
    To: str = Form(...),
    voice_agent_id: str = Query(...),
    welcome_message_audio_url: str = Query(default=''),
):
    """
    Twilio TwiML endpoint

    Called by Twilio when call connects (directly or via outbound webhook redirect).
    Returns TwiML XML with WebSocket connection instructions.

    Query params:
        voice_agent_id: UUID of the voice agent configuration
        welcome_message_audio_url: URL of the welcome message audio file
    """
    logger.info(f'TwiML requested for voice_agent_id: {voice_agent_id}')
    logger.info(f'Welcome message audio URL: {welcome_message_audio_url}')

    # Build WebSocket URL
    base_url = os.getenv('CALL_PROCESSING_BASE_URL', 'http://localhost:8003')

    # Convert https:// to wss:// (or http:// to ws://)
    if base_url.startswith('https://'):
        websocket_url = base_url.replace('https://', 'wss://')
    elif base_url.startswith('http://'):
        websocket_url = base_url.replace('http://', 'ws://')
    else:
        websocket_url = f'wss://{base_url}'

    websocket_url = f'{websocket_url}/webhooks/ws'

    logger.info(f'WebSocket URL: {websocket_url}')

    # Generate TwiML response
    response = VoiceResponse()

    # Play welcome message audio if URL is provided
    if welcome_message_audio_url:
        response.play(welcome_message_audio_url)
    else:
        logger.warning(
            'No welcome message audio URL provided, skipping welcome message'
        )

    connect = Connect()
    stream = Stream(url=websocket_url)

    # Pass parameters to WebSocket stream
    stream.parameter(name='voice_agent_id', value=voice_agent_id)
    stream.parameter(name='customer_number', value=To)
    stream.parameter(name='agent_number', value=From)

    connect.append(stream)
    response.append(connect)

    # Pause for 60 seconds before auto-hangup (adjust as needed)
    response.pause(length=60)

    twiml_xml = str(response)
    logger.info(f'Returning TwiML: {twiml_xml}')

    return Response(content=twiml_xml, media_type='application/xml')


@webhook_router.websocket('/ws')
@inject
async def websocket_endpoint(
    websocket: WebSocket,
    voice_agent_cache_service: VoiceAgentCacheService = Depends(
        Provide[ApplicationContainer.voice_agent_cache_service]
    ),
):
    """
    Twilio Media Stream WebSocket endpoint

    Handles bidirectional audio streaming with Pipecat pipeline.
    """
    await websocket.accept()
    logger.info('WebSocket connection accepted')

    try:
        # Create runner arguments and parse Twilio connection
        runner_args = WebSocketRunnerArguments(websocket=websocket)
        transport_type, call_data = await parse_telephony_websocket(
            runner_args.websocket
        )

        logger.info(f'Auto-detected transport: {transport_type}')
        logger.info(f'Call data: {call_data}')

        # Extract parameters from stream
        body_data = call_data.get('body', {})
        voice_agent_id = body_data.get('voice_agent_id')
        customer_number = body_data.get('customer_number')
        # agent_number = body_data.get('agent_number')

        if not voice_agent_id:
            logger.error('voice_agent_id not found in stream parameters')
            await websocket.close(code=1008, reason='Missing voice_agent_id')
            return

        if not customer_number:
            logger.warning(
                'customer_number not found in stream parameters, using empty string'
            )
            customer_number = ''

        logger.info(f'Voice agent ID: {voice_agent_id}')

        # Convert voice_agent_id to UUID
        try:
            agent_uuid = UUID(voice_agent_id)
        except ValueError:
            logger.error(f'Invalid UUID format for voice_agent_id: {voice_agent_id}')
            await websocket.close(code=1008, reason='Invalid voice_agent_id format')
            return

        # Fetch all configs from cache with API fallback
        configs = await voice_agent_cache_service.get_all_agent_configs(agent_uuid)

        logger.info('Successfully fetched all configs from cache')

        # Create Twilio frame serializer
        serializer = TwilioFrameSerializer(
            stream_sid=call_data['stream_id'],
            call_sid=call_data['call_id'],
            account_sid=configs['telephony_config']['credentials']['account_sid'],
            auth_token=configs['telephony_config']['credentials']['auth_token'],
        )

        # Create FastAPI WebSocket transport
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_in_passthrough=True,
                add_wav_header=False,  # Twilio doesn't need WAV header
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        confidence=0.7,  # Default is 0.7, can lower to 0.4-0.5 for faster detection
                        start_secs=0.2,  # Default is 0.2, keep it
                        stop_secs=0.2,  # KEY: Lower from default 0.8 for faster cutoff (should be 0.2 for smart turn detection)
                        min_volume=0.6,  # Default is 0.6, adjust based on your audio quality
                    ),
                ),  # Voice Activity Detection
                serializer=serializer,
            ),
        )

        # Run conversation pipeline
        pipecat_service = PipecatService()
        await pipecat_service.run_conversation(
            transport=transport,
            agent_config=configs['agent'],
            llm_config=configs['llm_config'],
            tts_config=configs['tts_config'],
            stt_config=configs['stt_config'],
            tools=configs['tools'],
            customer_number=customer_number,
        )

    except Exception as e:
        logger.error(f'Error in WebSocket endpoint: {e}', exc_info=True)
        if websocket.client_state.name != 'DISCONNECTED':
            await websocket.close(code=1011, reason='Internal error')
