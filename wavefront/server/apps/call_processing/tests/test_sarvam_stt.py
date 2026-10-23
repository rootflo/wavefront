"""The Sarvam STT reconnects after Sarvam drops the stream (e.g. a rate limit)."""

import asyncio
from typing import List

from pipecat.frames.frames import CancelFrame
from pipecat.services.sarvam.stt import SarvamSTTSettings

from call_processing.services.common.providers.sarvam_stt import (
    ReconnectingSarvamSTTService,
)


class FakeSocket:
    def __init__(self, fail: bool):
        self.fail = fail
        self.sent = 0

    async def transcribe(self, **kwargs):
        if self.fail:
            raise RuntimeError('received 1003 (unsupported data) Rate limit exceeded')
        self.sent += 1


class Harness:
    """A service whose Sarvam connection is faked; ``fail`` drops the next stream."""

    def __init__(self, fail_first: bool = True, connect_fails: int = 0):
        self.stt = ReconnectingSarvamSTTService(
            api_key='k',
            sample_rate=16000,
            settings=SarvamSTTSettings(model='saaras:v4'),
            reconnect_delays=(0.01, 0.02),
        )
        self.connects = 0
        self.disconnects = 0
        self.connect_fails = connect_fails
        self.stt._socket_client = FakeSocket(fail=fail_first)
        stt = self.stt

        async def connect():
            self.connects += 1
            if self.connect_fails:
                self.connect_fails -= 1
                stt._socket_client = None
            else:
                stt._socket_client = FakeSocket(fail=False)

        async def disconnect():
            self.disconnects += 1
            stt._socket_client = None

        stt._connect = connect
        stt._disconnect = disconnect
        # No pipeline here: run tasks on the loop directly
        stt.create_task = lambda coro, name=None: asyncio.create_task(coro)

        async def cancel_task(task, timeout=1.0):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        stt.cancel_task = cancel_task

    async def send(self) -> List:
        return [frame async for frame in self.stt.run_stt(b'\x00' * 640)]


async def _until(predicate, timeout: float = 2.0):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


async def test_dropped_stream_reconnects_without_flooding_errors():
    h = Harness()

    # The dropped socket: no ErrorFrame reaches the pipeline, one reconnect starts
    for _ in range(20):
        assert not any(frame is not None for frame in await h.send())
    await _until(lambda: h.connects == 1)
    assert h.disconnects == 1

    # Audio flows again on the new socket
    await h.send()
    assert h.stt._socket_client.sent == 1


async def test_failed_reconnect_retries_on_the_next_audio():
    h = Harness(connect_fails=1)

    await h.send()
    await _until(lambda: h.connects == 1 and h.stt._reconnect_task is None)
    assert h.stt._socket_client is None

    await h.send()  # no socket: schedules the next attempt
    await _until(lambda: h.connects == 2)
    await h.send()
    assert h.stt._socket_client.sent == 1


async def test_cancel_stops_a_pending_reconnect():
    h = Harness()
    h.stt._reconnect_delays = (5.0,)

    await h.send()
    assert h.stt._reconnect_task is not None
    await h.stt.cancel(CancelFrame())
    assert h.stt._reconnect_task is None
    assert h.connects == 0
    # Nothing is scheduled once the service is stopping
    await h.send()
    assert h.stt._reconnect_task is None
