"""The Sarvam STT reconnects after Sarvam drops the stream (e.g. a rate limit)."""

import asyncio
from typing import List

from pipecat.frames.frames import CancelFrame
from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings

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


def _reconnecting_update(gate: asyncio.Event):
    """Pipecat's language update: disconnect, then connect. ``gate`` holds it
    between the two, where the socket is missing and audio still arrives."""

    async def update(self, delta):
        await self._disconnect()
        await gate.wait()
        await self._connect()
        return {'language': None}

    return update


async def test_a_language_switch_is_not_mistaken_for_a_dropped_stream(monkeypatch):
    gate = asyncio.Event()
    monkeypatch.setattr(
        SarvamSTTService, '_update_settings', _reconnecting_update(gate)
    )
    h = Harness(fail_first=False)
    update = asyncio.create_task(
        h.stt._update_settings(SarvamSTTSettings(language='hi-IN'))
    )
    await _until(lambda: h.stt._socket_client is None)

    # Audio during the switch's own reconnect: dropped, but no reconnect of ours
    assert await h.send() == [None]
    assert h.stt._reconnect_task is None

    gate.set()
    await update
    assert h.connects == 1
    # Audio flows on the switch's socket at once, not after a backoff
    await h.send()
    assert h.stt._socket_client.sent == 1
    assert h.stt._reconnect_task is None


async def test_a_failed_switch_reconnect_is_retried_on_the_next_audio(monkeypatch):
    gate = asyncio.Event()
    gate.set()
    monkeypatch.setattr(
        SarvamSTTService, '_update_settings', _reconnecting_update(gate)
    )
    h = Harness(fail_first=False, connect_fails=1)

    await h.stt._update_settings(SarvamSTTSettings(language='hi-IN'))
    assert h.stt._socket_client is None

    await h.send()
    await _until(lambda: h.connects == 2)
    await h.send()
    assert h.stt._socket_client.sent == 1


async def test_a_pending_reconnect_never_opens_a_second_stream():
    h = Harness()
    h.stt._reconnect_delays = (0.05,)

    await h.send()  # the drop schedules our reconnect
    await _until(lambda: h.disconnects == 1)
    socket = FakeSocket(fail=False)
    h.stt._socket_client = socket  # something else reconnected meanwhile
    await _until(lambda: h.stt._reconnect_task is None)

    assert h.connects == 0
    assert h.stt._socket_client is socket
