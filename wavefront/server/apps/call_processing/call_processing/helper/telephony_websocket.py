"""
Telephony WebSocket parsing with Smartflo support.

Pipecat's ``parse_telephony_websocket`` auto-detects Smartflo as Twilio because both
use camelCase ``streamSid`` / ``callSid`` on the start event. This module extends
that behavior by detecting Smartflo first using fields unique to its protocol.

Smartflo start payload (see Smartflo bi-directional audio streaming docs):
  - ``start.direction`` (inbound/outbound)
  - ``start.from`` / ``start.to``
  - ``start.mediaFormat.bitRate`` / ``bitDepth`` (Twilio uses ``channels`` instead)
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from fastapi import WebSocket

from call_processing.log.logger import logger

# Hop-by-hop / handshake headers that are not Smartflo custom parameters
_STANDARD_WS_HEADERS = {
    'host',
    'connection',
    'upgrade',
    'origin',
    'user-agent',
    'accept',
    'accept-encoding',
    'accept-language',
    'cache-control',
    'pragma',
    'content-length',
    'content-type',
    'cookie',
    'sec-websocket-key',
    'sec-websocket-version',
    'sec-websocket-extensions',
    'sec-websocket-protocol',
}


def _normalize_header_key(key: str) -> str:
    """Normalize header names to snake_case param keys (voice-agent-id -> voice_agent_id)."""
    return key.strip().lower().replace('-', '_')


def _custom_parameters_from_headers(headers: Any) -> Dict[str, Any]:
    """
    Build custom parameters from Smartflo WebSocket handshake headers.

    Smartflo can send configured custom/auth headers on the WSS connection
    (start.customParameters is often empty in practice).
    """
    if not headers:
        return {}

    params: Dict[str, Any] = {}

    # Prefer an explicit JSON blob header when present
    for blob_key in (
        'customparameters',
        'custom-parameters',
        'custom_parameters',
        'x-custom-parameters',
        'x-customparameters',
    ):
        raw = headers.get(blob_key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                params.update(
                    {_normalize_header_key(str(k)): v for k, v in parsed.items()}
                )
            else:
                params[_normalize_header_key(blob_key)] = raw
        except (json.JSONDecodeError, TypeError):
            params[_normalize_header_key(blob_key)] = raw

    # Collect remaining non-standard headers as flat custom params
    try:
        items = headers.items()
    except AttributeError:
        items = dict(headers).items()

    for key, value in items:
        lower = key.lower()
        if lower in _STANDARD_WS_HEADERS or lower.startswith('sec-'):
            continue
        normalized = _normalize_header_key(key)
        # Don't overwrite values already taken from a JSON blob
        if normalized not in params and value is not None and value != '':
            params[normalized] = value

    return params


def _is_smartflo_start(message_data: dict) -> bool:
    """
    Return True if the message matches Smartflo's start event shape.
    """
    if message_data.get('event') != 'start':
        return False

    start = message_data.get('start') or {}
    if 'streamSid' not in start or 'callSid' not in start:
        return False

    media_format = start.get('mediaFormat') or {}

    # Distinctive Smartflo fields (not present on a typical Twilio start event)
    has_direction = 'direction' in start
    has_from_to = 'from' in start and 'to' in start
    has_smartflo_media_format = 'bitRate' in media_format or 'bitDepth' in media_format

    return has_direction or has_from_to or has_smartflo_media_format


def _detect_transport_type(message_data: dict) -> str:
    """Detect transport type, preferring Smartflo over Twilio when ambiguous."""
    if not message_data:
        return 'unknown'

    # Smartflo must be checked before Twilio — same streamSid/callSid shape
    if _is_smartflo_start(message_data):
        logger.debug('Auto-detected: SMARTFLO')
        return 'smartflo'

    # Twilio
    if (
        message_data.get('event') == 'start'
        and 'start' in message_data
        and 'streamSid' in message_data.get('start', {})
        and 'callSid' in message_data.get('start', {})
    ):
        logger.debug('Auto-detected: TWILIO')
        return 'twilio'

    # Telnyx
    if (
        'stream_id' in message_data
        and 'start' in message_data
        and 'call_control_id' in message_data.get('start', {})
    ):
        logger.debug('Auto-detected: TELNYX')
        return 'telnyx'

    # Plivo
    if (
        'start' in message_data
        and 'streamId' in message_data.get('start', {})
        and 'callId' in message_data.get('start', {})
    ):
        logger.debug('Auto-detected: PLIVO')
        return 'plivo'

    # Exotel
    if (
        message_data.get('event') == 'start'
        and 'start' in message_data
        and 'stream_sid' in message_data.get('start', {})
        and 'call_sid' in message_data.get('start', {})
        and 'account_sid' in message_data.get('start', {})
    ):
        logger.debug('Auto-detected: EXOTEL')
        return 'exotel'

    return 'unknown'


def _extract_call_data(
    transport_type: str,
    call_data_raw: dict,
    headers: Any = None,
) -> Dict[str, Any]:
    """Extract normalized call_data for the detected transport type."""
    if transport_type == 'smartflo':
        start_data = call_data_raw.get('start', {})
        header_params = _custom_parameters_from_headers(headers)
        logger.info(f'Smartflo custom parameters from headers: {header_params}')
        return {
            'stream_id': start_data.get('streamSid') or call_data_raw.get('streamSid'),
            'call_id': start_data.get('callSid'),
            'account_sid': start_data.get('accountSid'),
            'from': start_data.get('from', ''),
            'to': start_data.get('to', ''),
            'direction': start_data.get('direction', ''),
            'body': header_params,
        }

    if transport_type == 'twilio':
        start_data = call_data_raw.get('start', {})
        return {
            'stream_id': start_data.get('streamSid'),
            'call_id': start_data.get('callSid'),
            'body': start_data.get('customParameters', {}),
        }

    if transport_type == 'telnyx':
        return {
            'stream_id': call_data_raw.get('stream_id'),
            'call_control_id': call_data_raw.get('start', {}).get('call_control_id'),
            'outbound_encoding': call_data_raw.get('start', {})
            .get('media_format', {})
            .get('encoding'),
            'from': call_data_raw.get('start', {}).get('from', ''),
            'to': call_data_raw.get('start', {}).get('to', ''),
        }

    if transport_type == 'plivo':
        start_data = call_data_raw.get('start', {})
        return {
            'stream_id': start_data.get('streamId'),
            'call_id': start_data.get('callId'),
        }

    if transport_type == 'exotel':
        start_data = call_data_raw.get('start', {})
        return {
            'stream_id': start_data.get('stream_sid'),
            'call_id': start_data.get('call_sid'),
            'account_sid': start_data.get('account_sid'),
            'from': start_data.get('from', ''),
            'to': start_data.get('to', ''),
            'custom_parameters': start_data.get('custom_parameters', ''),
        }

    return {}


async def parse_telephony_websocket(
    websocket: WebSocket,
) -> Tuple[str, Dict[str, Any]]:
    """
    Parse telephony WebSocket handshake messages with Smartflo support.

    Drop-in extension of Pipecat's ``parse_telephony_websocket``. Reads the first
    two WebSocket text messages, detects the provider, and returns normalized
    ``(transport_type, call_data)``.

    Smartflo call_data::

        {
            "stream_id": str,
            "call_id": str,
            "account_sid": str | None,
            "from": str,
            "to": str,
            "direction": str,
            "body": dict,              # custom params (headers preferred)
            "custom_parameters": dict,  # same as body
        }
    """
    # Capture handshake headers before reading messages (Smartflo custom params)
    ws_headers = websocket.headers
    logger.debug(f'Telephony WS headers: {dict(ws_headers)}')

    message_stream = websocket.iter_text()
    first_message: Dict[str, Any] = {}
    second_message: Dict[str, Any] = {}

    try:
        first_message_raw = await message_stream.__anext__()
        logger.debug(f'First telephony WS message: {first_message_raw}')
        first_message = json.loads(first_message_raw) if first_message_raw else {}
    except json.JSONDecodeError:
        pass
    except StopAsyncIteration:
        raise ValueError(
            'WebSocket closed before receiving telephony handshake messages'
        )

    try:
        second_message_raw = await message_stream.__anext__()
        logger.debug(f'Second telephony WS message: {second_message_raw}')
        second_message = json.loads(second_message_raw) if second_message_raw else {}
    except json.JSONDecodeError:
        pass
    except StopAsyncIteration:
        logger.warning('Only received one WebSocket message, expected two')

    detected_type_first = _detect_transport_type(first_message)
    detected_type_second = _detect_transport_type(second_message)

    if detected_type_first != 'unknown':
        transport_type = detected_type_first
        call_data_raw = first_message
        logger.debug(f'Detected transport: {transport_type} (from first message)')
    elif detected_type_second != 'unknown':
        transport_type = detected_type_second
        call_data_raw = second_message
        logger.debug(f'Detected transport: {transport_type} (from second message)')
    else:
        transport_type = 'unknown'
        call_data_raw = second_message or first_message
        logger.warning('Could not auto-detect transport type')

    call_data = _extract_call_data(transport_type, call_data_raw, headers=ws_headers)
    logger.debug(f'Parsed - Type: {transport_type}, Data: {call_data}')
    return transport_type, call_data
