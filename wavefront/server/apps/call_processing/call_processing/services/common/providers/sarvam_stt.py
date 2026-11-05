"""Sarvam streaming STT that recovers from a dropped WebSocket.

Pipecat's ``SarvamSTTService`` never reconnects on its own: once Sarvam closes
the stream (e.g. ``1003 Rate limit exceeded``), every audio chunk fails with an
``ErrorFrame`` (~50 per second) and the caller is not heard again until
something else reconnects the service (a language switch). This subclass drops
audio while the socket is down and reconnects with a backoff instead.

A settings change (a language switch) reconnects on its own, and the socket is
briefly missing while it does. That is not a drop: reconnecting then would throw
away the caller's audio for a whole backoff delay and open a second stream.
"""

import asyncio
from typing import AsyncGenerator, Optional, Sequence, Set

from pipecat.frames.frames import CancelFrame, EndFrame, ErrorFrame, Frame
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.settings import STTSettings

from call_processing.log.logger import logger

# Seconds to wait before each reconnect attempt; the last one repeats. Sarvam
# asks for "a short backoff" after a rate limit.
RECONNECT_DELAYS_SECS: Sequence[float] = (1.0, 2.0, 4.0, 8.0, 15.0)


class ReconnectingSarvamSTTService(SarvamSTTService):
    # Services of this process holding an open Sarvam stream. Logged on every
    # connect / disconnect: a count that keeps growing across calls is a leak,
    # and Sarvam rate-limits a key with too many concurrent streams.
    _open_streams: Set[int] = set()

    def __init__(
        self,
        *args,
        reconnect_delays: Sequence[float] = RECONNECT_DELAYS_SECS,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._reconnect_delays = tuple(reconnect_delays)
        self._reconnect_task: Optional[asyncio.Task] = None
        # Consecutive drops without a message from Sarvam in between
        self._drops = 0
        self._stopping = False
        # A settings change is reconnecting the socket itself
        self._updating_settings = False

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if self._reconnect_task is not None:
            yield None  # Reconnecting: the audio has nowhere to go
            return
        if self._socket_client is None:
            if self._updating_settings:
                yield None  # The settings change is reconnecting
                return
            # The connect at start (or a reconnect for a settings change) failed
            self._schedule_reconnect('not connected')
            yield None
            return
        async for frame in super().run_stt(audio):
            if isinstance(frame, ErrorFrame):
                self._schedule_reconnect(frame.error)
                yield None
            else:
                yield frame

    async def _connect(self):
        await super()._connect()
        if self._socket_client is not None:
            self._open_streams.add(id(self))
            logger.info(
                f'Sarvam STT stream open (open in this process: '
                f'{len(self._open_streams)})'
            )

    async def _disconnect(self):
        await super()._disconnect()
        if id(self) in self._open_streams:
            self._open_streams.discard(id(self))
            logger.info(
                f'Sarvam STT stream closed (open in this process: '
                f'{len(self._open_streams)})'
            )

    async def _handle_message(self, message):
        self._drops = 0
        await super()._handle_message(message)

    def _schedule_reconnect(self, reason: str) -> None:
        if self._stopping or self._reconnect_task is not None:
            return
        delay = self._reconnect_delays[
            min(self._drops, len(self._reconnect_delays) - 1)
        ]
        self._drops += 1
        logger.warning(f'Sarvam STT stream lost ({reason}); reconnecting in {delay}s')
        self._reconnect_task = self.create_task(self._reconnect(delay), 'reconnect')

    async def _reconnect(self, delay: float) -> None:
        try:
            await self._disconnect()
            await asyncio.sleep(delay)
            # A settings change may have reconnected meanwhile: never open a
            # second stream over it
            if self._stopping or self._socket_client is not None:
                return
            await self._connect()
        finally:
            if self._reconnect_task is asyncio.current_task():
                self._reconnect_task = None
        # A failed connect leaves no socket: the next audio chunk schedules the
        # next attempt, with a longer delay.

    async def _cancel_reconnect(self) -> None:
        task = self._reconnect_task
        self._reconnect_task = None
        if task is not None:
            await self.cancel_task(task)

    async def _update_settings(self, delta: STTSettings):
        # A settings change reconnects itself; never race it with our reconnect
        await self._cancel_reconnect()
        self._updating_settings = True
        try:
            return await super()._update_settings(delta)
        finally:
            self._updating_settings = False

    async def stop(self, frame: EndFrame):
        self._stopping = True
        await self._cancel_reconnect()
        await super().stop(frame)

    async def cancel(self, frame: CancelFrame):
        self._stopping = True
        await self._cancel_reconnect()
        await super().cancel(frame)
