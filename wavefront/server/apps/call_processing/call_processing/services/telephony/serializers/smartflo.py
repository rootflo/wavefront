"""Smartflo (Tata Tele) Media Streams WebSocket protocol serializer for Pipecat.

Smartflo streams bi-directional audio over a WebSocket using a Twilio-like event
protocol. Smartflo sends us ``connected``, ``start``, ``media``, ``dtmf``, ``stop``
and ``mark`` events; we send back ``media``, ``mark`` and ``clear`` events.

Audio is always 8kHz mono G.711 µ-law (``audio/x-mulaw``) encoded as base64.
"""

import base64
import json
from typing import Any, Dict, Optional

from loguru import logger

from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.audio.utils import create_stream_resampler, pcm_to_ulaw, ulaw_to_pcm
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputDTMFFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

# One µ-law frame is 20ms of 8kHz mono audio. Smartflo requires outbound media
# payloads to be a multiple of this size, otherwise audio gaps occur on the call.
MULAW_FRAME_SIZE = 160

# 0xFF is the µ-law encoding of silence, used to pad a partial trailing frame.
MULAW_SILENCE_BYTE = b'\xff'


class SmartfloFrameSerializer(FrameSerializer):
    """Serializer for the Smartflo Media Streams WebSocket protocol.

    Converts between Pipecat frames and Smartflo WebSocket events, handling µ-law
    conversion, DTMF input, interruptions (``clear``) and mark synchronization.

    Outbound audio is buffered so every ``media`` event carries a payload that is a
    multiple of 160 bytes, as required by Smartflo.

    A ``mark`` event can be sent by pushing an ``OutputTransportMessageFrame`` with the
    mark payload; incoming ``mark`` events are pushed downstream as
    ``InputTransportMessageFrame``.
    """

    class InputParams(FrameSerializer.InputParams):
        """Configuration parameters for SmartfloFrameSerializer.

        Parameters:
            smartflo_sample_rate: Sample rate used by Smartflo, always 8000 Hz.
            sample_rate: Optional override for pipeline input sample rate.
            ignore_rtvi_messages: Inherited from base FrameSerializer, defaults to True.
        """

        smartflo_sample_rate: int = 8000
        sample_rate: Optional[int] = None

    def __init__(
        self,
        stream_sid: str,
        call_sid: Optional[str] = None,
        account_sid: Optional[str] = None,
        params: Optional[InputParams] = None,
    ):
        """Initialize the SmartfloFrameSerializer.

        Args:
            stream_sid: The Smartflo Stream SID (``start.streamSid``).
            call_sid: The associated Smartflo Call SID (``start.callSid``).
            account_sid: The Smartflo Account SID (``start.accountSid``).
            params: Configuration parameters.
        """
        super().__init__(params or SmartfloFrameSerializer.InputParams())

        self._stream_sid = stream_sid
        self._call_sid = call_sid
        self._account_sid = account_sid

        self._smartflo_sample_rate = self._params.smartflo_sample_rate
        self._sample_rate = 0  # Pipeline input rate

        self._input_resampler = create_stream_resampler()
        self._output_resampler = create_stream_resampler()

        self._output_buffer = bytearray()
        self._chunk = 0

        self._from_number: Optional[str] = None
        self._to_number: Optional[str] = None
        self._direction: Optional[str] = None
        self._custom_parameters: Dict[str, Any] = {}

    @property
    def stream_sid(self) -> str:
        """The Stream SID of the current stream."""
        return self._stream_sid

    @property
    def call_sid(self) -> Optional[str]:
        """The Call SID of the current stream."""
        return self._call_sid

    @property
    def custom_parameters(self) -> Dict[str, Any]:
        """Custom parameters received in the Smartflo ``start`` event."""
        return self._custom_parameters

    async def setup(self, frame: StartFrame):
        """Sets up the serializer with pipeline configuration.

        Args:
            frame: The StartFrame containing pipeline configuration.
        """
        self._sample_rate = self._params.sample_rate or frame.audio_in_sample_rate

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Serializes a Pipecat frame to a Smartflo WebSocket event.

        Args:
            frame: The Pipecat frame to serialize.

        Returns:
            Serialized data as string, or None if the frame isn't handled.
        """
        if isinstance(frame, (EndFrame, CancelFrame)):
            # Flush whatever audio is left so the tail of the last utterance is played.
            return self._pop_media_message(flush=True)
        elif isinstance(frame, InterruptionFrame):
            # Smartflo empties its playback buffer and echoes back any pending marks.
            self._output_buffer.clear()
            return json.dumps({'event': 'clear', 'streamSid': self._stream_sid})
        elif isinstance(frame, AudioRawFrame):
            # Output: Convert PCM at frame's rate to 8kHz µ-law for Smartflo
            serialized_data = await pcm_to_ulaw(
                frame.audio,
                frame.sample_rate,
                self._smartflo_sample_rate,
                self._output_resampler,
            )
            if not serialized_data:
                # Ignoring in case we don't have audio
                return None

            self._output_buffer.extend(serialized_data)
            return self._pop_media_message()
        elif isinstance(
            frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)
        ):
            if self.should_ignore_frame(frame):
                return None
            return json.dumps(frame.message)

        # Return None for unhandled frames
        return None

    def _pop_media_message(self, flush: bool = False) -> Optional[str]:
        """Build a media event from buffered µ-law audio, keeping a 160 byte alignment.

        Args:
            flush: Pad a partial trailing frame with silence instead of buffering it.

        Returns:
            The serialized media event, or None if there isn't enough audio yet.
        """
        if flush:
            remainder = len(self._output_buffer) % MULAW_FRAME_SIZE
            if remainder:
                self._output_buffer.extend(
                    MULAW_SILENCE_BYTE * (MULAW_FRAME_SIZE - remainder)
                )

        size = (len(self._output_buffer) // MULAW_FRAME_SIZE) * MULAW_FRAME_SIZE
        if not size:
            return None

        chunk = bytes(self._output_buffer[:size])
        del self._output_buffer[:size]

        self._chunk += 1
        message = {
            'event': 'media',
            'streamSid': self._stream_sid,
            'media': {
                'payload': base64.b64encode(chunk).decode('utf-8'),
                'chunk': self._chunk,
            },
        }

        return json.dumps(message)

    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Deserializes Smartflo WebSocket data to Pipecat frames.

        Args:
            data: The raw WebSocket data from Smartflo.

        Returns:
            A Pipecat frame corresponding to the Smartflo event, or None if unhandled.
        """
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(f'Failed to parse Smartflo message: {data}')
            return None

        event = message.get('event')

        if event == 'media':
            payload_base64 = message.get('media', {}).get('payload')
            if not payload_base64:
                return None

            payload = base64.b64decode(payload_base64)

            # Input: Convert Smartflo's 8kHz µ-law to PCM at pipeline input rate
            deserialized_data = await ulaw_to_pcm(
                payload,
                self._smartflo_sample_rate,
                self._sample_rate,
                self._input_resampler,
            )
            if not deserialized_data:
                # Ignoring in case we don't have audio
                return None

            return InputAudioRawFrame(
                audio=deserialized_data, num_channels=1, sample_rate=self._sample_rate
            )
        elif event == 'dtmf':
            digit = message.get('dtmf', {}).get('digit')
            try:
                return InputDTMFFrame(KeypadEntry(digit))
            except ValueError:
                # Handle case where string doesn't match any enum value
                logger.warning(f'Invalid Smartflo DTMF digit: {digit}')
                return None
        elif event == 'start':
            self._handle_start(message)
            return None
        elif event == 'mark':
            # Playback of a previously sent media chunk finished, or a pending mark was
            # flushed after a clear. Surfaced downstream so the app can react to it.
            return InputTransportMessageFrame(message=message)
        elif event == 'stop':
            reason = message.get('stop', {}).get('reason')
            logger.debug(f'Smartflo stream {self._stream_sid} stopped: {reason}')
            return None
        elif event == 'connected':
            logger.debug('Smartflo WebSocket connected')
            return None

        return None

    def _handle_start(self, message: dict):
        """Capture stream metadata from the Smartflo ``start`` event."""
        start = message.get('start', {})

        self._stream_sid = (
            start.get('streamSid') or message.get('streamSid') or self._stream_sid
        )
        self._call_sid = start.get('callSid') or self._call_sid
        self._account_sid = start.get('accountSid') or self._account_sid
        self._from_number = start.get('from')
        self._to_number = start.get('to')
        self._direction = start.get('direction')
        self._custom_parameters = start.get('customParameters') or {}

        logger.debug(
            f'Smartflo stream started: stream_sid={self._stream_sid}, '
            f'call_sid={self._call_sid}, direction={self._direction}, '
            f'from={self._from_number}, to={self._to_number}'
        )
