"""Phone call media streams: handshake -> voice agent -> transport -> conversation.

Two entry points, both on an accepted FastAPI websocket:
    ``handle_stream``          Twilio / Exotel / Smartflo streams that carry the
                               ``voice_agent_id`` in their stream parameters.
    ``handle_exotel_inbound``  Exotel AppBazaar voicebot: the agent is looked up
                               by the called (inbound) number.
"""

import html
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import WebSocket
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.serializers.exotel import ExotelFrameSerializer
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.log.logger import logger
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from call_processing.services.telephony.conversation import TelephonyConversation
from call_processing.services.telephony.serializers.smartflo import (
    SmartfloFrameSerializer,
)
from call_processing.services.telephony.websocket_parser import (
    parse_telephony_websocket,
)

# WebSocket close code for a stream we cannot serve (bad / missing parameters)
_POLICY_VIOLATION = 1008
_INTERNAL_ERROR = 1011


def normalize_indian_phone_number(phone_number: str) -> str:
    """
    Normalize Indian phone number to E.164 format.

    Converts Indian national format (0xxxxxxxxxx) to E.164 format (+91xxxxxxxxxx).

    Examples:
        "01234567890" -> "+911234567890"
        "+911234567890" -> "+911234567890"
        "911234567890" -> "+911234567890"
    """
    # Remove any whitespace
    phone_number = phone_number.strip()

    # If already in E.164 format with +91, return as is
    if phone_number.startswith('+91'):
        return phone_number

    # If starts with 91 but no +, add +
    if phone_number.startswith('91') and len(phone_number) >= 12:
        return f'+{phone_number}'

    # If starts with 0 (Indian national format), replace with +91
    if phone_number.startswith('0'):
        return f'+91{phone_number[1:]}'

    # If it's just the number without country code, add +91
    if len(phone_number) == 10:
        return f'+91{phone_number}'

    # Return as is if we can't determine format
    return phone_number


def _mask(number: str) -> str:
    return f'***{number[-4:]}' if len(number) > 4 else '****'


@dataclass
class _StreamParams:
    voice_agent_id: Optional[str]
    customer_number: str
    agent_number: str
    call_direction: Optional[str] = None


def _stream_params(transport_type: str, call_data: Dict[str, Any]) -> _StreamParams:
    """Read the agent and the call's numbers from a provider's start message."""
    if transport_type == 'twilio':
        body_data = call_data.get('body', {})
        return _StreamParams(
            voice_agent_id=body_data.get('voice_agent_id'),
            customer_number=body_data.get('customer_number'),
            agent_number=body_data.get('agent_number', ''),
        )

    if transport_type == 'exotel':
        custom_parameters = call_data.get('custom_parameters', {})
        logger.info(f'Exotel custom_parameters: {custom_parameters}')
        # custom_parameters comes as {'{"voice_agent_id": "..."}': ''}
        # The key is a JSON string from json.dumps() in exotel_service
        voice_agent_id = None
        for key in custom_parameters:
            try:
                parsed = json.loads(html.unescape(key))
                if isinstance(parsed, dict) and 'voice_agent_id' in parsed:
                    voice_agent_id = parsed['voice_agent_id']
                    break
            except (json.JSONDecodeError, TypeError):
                continue
        return _StreamParams(
            voice_agent_id=voice_agent_id,
            customer_number=call_data.get('from', ''),
            agent_number=call_data.get('to', ''),
        )

    # smartflo
    body_data = call_data.get('body', {}) or {}
    params = body_data if isinstance(body_data, dict) and body_data else {}
    call_direction = call_data.get('direction', None)
    if call_direction == 'inbound':
        customer_number = call_data.get('from', '')
        agent_number = call_data.get('to', '')
    else:
        customer_number = call_data.get('to', '')
        agent_number = call_data.get('from', '')
    return _StreamParams(
        voice_agent_id=params.get('voice_agent_id'),
        customer_number=customer_number,
        agent_number=agent_number,
        call_direction=call_direction,
    )


def _create_serializer(
    provider: str, call_data: Dict[str, Any], credentials: Dict[str, Any]
) -> Optional[FrameSerializer]:
    if provider == 'twilio':
        return TwilioFrameSerializer(
            stream_sid=call_data['stream_id'],
            call_sid=call_data['call_id'],
            account_sid=credentials['account_sid'],
            auth_token=credentials['auth_token'],
        )
    if provider == 'exotel':
        return ExotelFrameSerializer(
            stream_sid=call_data['stream_id'],
            call_sid=call_data.get('call_id'),
        )
    if provider == 'smartflo':
        return SmartfloFrameSerializer(
            stream_sid=call_data['stream_id'],
            call_sid=call_data.get('call_id'),
        )
    return None


class TelephonySessionService:
    def __init__(
        self,
        voice_agent_cache_service: VoiceAgentCacheService,
        app_settings: CallProcessingAppSettings,
    ):
        self.voice_agent_cache_service = voice_agent_cache_service
        self.app_settings = app_settings

    async def handle_stream(self, websocket: WebSocket) -> None:
        """Media stream that names its voice agent in the stream parameters."""
        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)
            logger.info(f'Auto-detected transport: {transport_type}')
            logger.debug(f'Call data: {call_data}')

            if transport_type not in ('twilio', 'exotel', 'smartflo'):
                logger.error(f'Unknown transport type: {transport_type}')
                await websocket.close(
                    code=_POLICY_VIOLATION,
                    reason=f'Unknown transport: {transport_type}',
                )
                return

            params = _stream_params(transport_type, call_data)
            if not params.voice_agent_id:
                logger.error('voice_agent_id not found in stream parameters')
                await websocket.close(
                    code=_POLICY_VIOLATION, reason='Missing voice_agent_id'
                )
                return

            customer_number = params.customer_number
            if not customer_number:
                logger.warning(
                    'customer_number not found in stream parameters, using empty string'
                )
                customer_number = ''

            logger.info(f'Voice agent ID: {params.voice_agent_id}')
            configs = await self._load_configs(websocket, params.voice_agent_id)
            if configs is None:
                return

            # The serializer follows the agent's telephony config
            provider = configs['telephony_config'].get('provider', 'twilio')
            serializer = _create_serializer(
                provider, call_data, configs['telephony_config']['credentials']
            )
            if serializer is None:
                logger.error(f'Unsupported telephony provider: {provider}')
                await websocket.close(
                    code=_POLICY_VIOLATION, reason=f'Unsupported provider: {provider}'
                )
                return

            await self._run(
                websocket,
                serializer,
                configs,
                provider=transport_type,
                call_id=call_data.get('call_id', ''),
                call_direction=params.call_direction or 'outbound',
                customer_number=customer_number,
                agent_number=params.agent_number,
            )
        except Exception as e:
            logger.error(f'Error in WebSocket endpoint: {e}', exc_info=True)
            await self._close_on_error(websocket)

    async def handle_exotel_inbound(self, websocket: WebSocket) -> None:
        """Exotel AppBazaar voicebot: the agent is found by the called number."""
        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)
            logger.info(f'Auto-detected transport: {transport_type}')

            if transport_type != 'exotel':
                logger.error(f'Expected Exotel transport, got: {transport_type}')
                await websocket.close(
                    code=_POLICY_VIOLATION,
                    reason=f'Unexpected transport type: {transport_type}',
                )
                return

            call_sid = call_data.get('call_id', '')
            from_number = call_data.get('from', '')
            to_number = call_data.get('to', '')
            logger.info(
                f'Exotel call: CallSid={call_sid}, From={_mask(from_number)}, '
                f'To={_mask(to_number)}'
            )

            if not to_number:
                logger.error('No "to" number found in Exotel call data')
                await websocket.close(
                    code=_POLICY_VIOLATION, reason='Missing "to" number in call data'
                )
                return

            # The database stores E.164; Exotel sends Indian numbers as 0xxxxxxxxxx
            normalized_to_number = normalize_indian_phone_number(to_number)
            normalized_from_number = normalize_indian_phone_number(from_number)
            masked_to = _mask(normalized_to_number)

            logger.info(f'Looking up agent by inbound number: {masked_to}')
            agent = await self.voice_agent_cache_service.get_agent_by_inbound_number(
                normalized_to_number
            )
            if not agent:
                logger.error(
                    f'No voice agent found for Exotel inbound number: {masked_to}'
                )
                await websocket.close(
                    code=_POLICY_VIOLATION,
                    reason='No voice agent configured for this number',
                )
                return

            voice_agent_id = agent['id']
            logger.info(
                f'Agent found for Exotel inbound {masked_to}: {voice_agent_id} ({agent["name"]})'
            )
            configs = await self._load_configs(websocket, voice_agent_id)
            if configs is None:
                return

            logger.info(f'Starting Pipecat pipeline for Exotel call {call_sid}')
            await self._run(
                websocket,
                _create_serializer('exotel', call_data, {}),
                configs,
                provider=transport_type,
                call_id=call_sid,
                call_direction='inbound',
                customer_number=normalized_from_number,
                agent_number=normalized_to_number,
            )
        except Exception as e:
            logger.error(f'Error in Exotel WebSocket endpoint: {e}', exc_info=True)
            await self._close_on_error(websocket)

    # ------------------------------------------------------------------ helpers

    async def _load_configs(
        self, websocket: WebSocket, voice_agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """All of the agent's configs (cache with API fallback), or None if closed."""
        try:
            agent_uuid = UUID(voice_agent_id)
        except ValueError:
            logger.error(f'Invalid UUID format for voice_agent_id: {voice_agent_id}')
            await websocket.close(
                code=_POLICY_VIOLATION, reason='Invalid voice_agent_id format'
            )
            return None
        configs = await self.voice_agent_cache_service.get_all_agent_configs(agent_uuid)
        logger.info('Successfully fetched all configs from cache')
        return configs

    async def _run(
        self,
        websocket: WebSocket,
        serializer: FrameSerializer,
        configs: Dict[str, Any],
        *,
        provider: str,
        call_id: str,
        call_direction: str,
        customer_number: str,
        agent_number: str,
    ) -> None:
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_in_passthrough=True,
                add_wav_header=False,  # Telephony streams take raw audio
                serializer=serializer,
            ),
        )
        conversation = TelephonyConversation(
            self.app_settings,
            provider=provider,
            call_id=call_id,
            call_direction=call_direction,
            customer_number=customer_number,
            agent_number=agent_number,
        )
        await conversation.run(transport, configs)

    @staticmethod
    async def _close_on_error(websocket: WebSocket) -> None:
        if websocket.client_state.name != 'DISCONNECTED':
            await websocket.close(code=_INTERNAL_ERROR, reason='Internal error')
