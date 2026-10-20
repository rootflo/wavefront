"""End-to-end signaling: create room -> real aiortc offer -> join rules -> cleanup.

The Pipecat pipeline itself is faked; everything else (HTTP routes, Redis rooms,
SmallWebRTC peer connection, session lifecycle) is real. Needs a local Redis.
"""

import asyncio
import uuid
from dataclasses import replace
from unittest.mock import MagicMock

import httpx
import pytest
from aiortc import RTCPeerConnection
from dependency_injector import providers
from redis import Redis

from call_processing.di import application_container
from call_processing.server import app
from call_processing.services import pipecat_service as pipecat_service_module

PASSTHROUGH = {'X-Passthrough': 'test-passthrough-secret'}
AGENT_ID = str(uuid.uuid4())


@pytest.fixture
def pipeline_calls(monkeypatch):
    """Replace the pipeline with one that records its arguments and waits."""
    calls = []

    async def fake_run_conversation(self, **kwargs):
        calls.append(kwargs)
        await asyncio.Event().wait()  # until the session is cancelled

    monkeypatch.setattr(
        pipecat_service_module.PipecatService,
        'run_conversation',
        fake_run_conversation,
    )
    return calls


@pytest.fixture
async def client(pipeline_calls):
    try:
        Redis(socket_connect_timeout=1).ping()
    except Exception:
        pytest.skip('Redis is not reachable')

    configs = {
        'agent': {'id': AGENT_ID, 'name': 'test'},
        'llm_config': {},
        'tts_config': {},
        'stt_config': {},
        'tools': [],
    }
    fake_cache = MagicMock()

    async def get_all_agent_configs(agent_id):
        return configs

    fake_cache.get_all_agent_configs = get_all_agent_configs

    application_container.voice_agent_cache_service.override(
        providers.Object(fake_cache)
    )
    application_container.webrtc_session_service.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url='http://test'
    ) as http_client:
        yield http_client
    await application_container.webrtc_session_service().close()
    application_container.voice_agent_cache_service.reset_override()
    application_container.webrtc_session_service.reset()


async def _create_room(client):
    response = await client.post(
        '/api/webrtc/rooms', json={'voice_agent_id': AGENT_ID}, headers=PASSTHROUGH
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _make_offer():
    pc = RTCPeerConnection()
    pc.addTransceiver('audio', direction='sendrecv')
    await pc.setLocalDescription(await pc.createOffer())
    return pc


def _offer_body(pc, room, **overrides):
    request_data = {
        'room_id': room['room_id'],
        'voice_agent_id': room['voice_agent_id'],
        'join_token': room['join_token'],
    }
    request_data.update(overrides)
    return {
        'sdp': pc.localDescription.sdp,
        'type': pc.localDescription.type,
        'requestData': request_data,
    }


async def test_create_room_returns_credentials_and_public_signaling_url(client):
    room = await _create_room(client)

    assert room['voice_agent_id'] == AGENT_ID
    assert room['room_id'] and room['join_token']
    assert room['signaling_url'].endswith('/api/webrtc')


async def test_create_room_requires_passthrough_auth(client):
    response = await client.post('/api/webrtc/rooms', json={'voice_agent_id': AGENT_ID})
    assert response.status_code == 401


async def test_offer_joins_room_runs_16k_pipeline_and_cleans_up(client, pipeline_calls):
    room = await _create_room(client)
    pc = await _make_offer()
    try:
        response = await client.post('/api/webrtc/offer', json=_offer_body(pc, room))

        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer['type'] == 'answer' and answer['pc_id']
        assert 'wf_webrtc_affinity' in response.headers['set-cookie']

        await asyncio.sleep(0.5)  # let the session task start the pipeline
        assert len(pipeline_calls) == 1
        call = pipeline_calls[0]
        assert call['provider'] == 'webrtc'
        assert call['call_id'] == room['room_id']
        assert call['audio_in_sample_rate'] == 16000
        assert call['audio_out_sample_rate'] == 16000
        assert call['idle_timeout_secs'] == 300

        session_service = application_container.webrtc_session_service()
        assert session_service.active_sessions == 1
        record = session_service.room_service.get_room(room['room_id'])
        assert record['status'] == 'joined'
        assert record['pc_id'] == answer['pc_id']
        assert record['instance_id'] == session_service.instance_id

        # Same token again: rejected, not a second pipeline
        again = await _make_offer()
        try:
            second = await client.post(
                '/api/webrtc/offer', json=_offer_body(again, room)
            )
        finally:
            await again.close()
        assert second.status_code == 409
        assert second.json()['error'] == 'room_already_joined'
        assert len(pipeline_calls) == 1

        # Shutdown cancels the session and ends the room
        await session_service.close()
        assert session_service.active_sessions == 0
        assert session_service.room_service.get_room(room['room_id']) is None
    finally:
        await pc.close()


async def _wait_until(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.1)
    return predicate()


@pytest.mark.parametrize(
    'limit',
    ['max_session_secs', 'connect_timeout_secs'],
)
async def test_session_is_cleaned_up_at_the_time_limits(client, limit):
    session_service = application_container.webrtc_session_service()
    session_service.webrtc_settings = replace(
        session_service.webrtc_settings, **{limit: 1}
    )
    room = await _create_room(client)
    pc = await _make_offer()
    try:
        response = await client.post('/api/webrtc/offer', json=_offer_body(pc, room))
        assert response.status_code == 200, response.text
        assert session_service.active_sessions == 1

        # The test peer never completes ICE, so both limits end the session
        assert await _wait_until(lambda: session_service.active_sessions == 0)
        assert session_service.room_service.get_room(room['room_id']) is None
    finally:
        await pc.close()


async def test_wrong_token_is_rejected_and_room_stays_joinable(client):
    room = await _create_room(client)
    pc = await _make_offer()
    try:
        bad = await client.post(
            '/api/webrtc/offer', json=_offer_body(pc, room, join_token='nope')
        )
        assert bad.status_code == 401
        assert bad.json()['error'] == 'invalid_join_token'

        good = await client.post('/api/webrtc/offer', json=_offer_body(pc, room))
        assert good.status_code == 200, good.text
    finally:
        await pc.close()


async def test_unknown_room_is_expired(client):
    room = await _create_room(client)
    room['room_id'] = uuid.uuid4().hex
    pc = await _make_offer()
    try:
        response = await client.post('/api/webrtc/offer', json=_offer_body(pc, room))
    finally:
        await pc.close()
    assert response.status_code == 410
    assert response.json()['error'] == 'room_expired'


async def test_ice_for_a_connection_owned_by_another_instance_is_sticky_required(
    client,
):
    response = await client.patch(
        '/api/webrtc/offer',
        json={
            'pc_id': 'SmallWebRTCConnection-unknown',
            'candidates': [
                {
                    'candidate': 'candidate:1 1 UDP 1 127.0.0.1 9 typ host',
                    'sdp_mid': '0',
                    'sdp_mline_index': 0,
                }
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()['error'] == 'sticky_required'


async def test_restart_pc_renegotiation_keeps_the_session_reachable(client):
    """restart_pc gives the connection a new pc_id; ICE PATCH / offers with it must not 409."""
    room = await _create_room(client)
    pc = await _make_offer()
    retry = await _make_offer()
    try:
        first = await client.post('/api/webrtc/offer', json=_offer_body(pc, room))
        assert first.status_code == 200, first.text
        old_pc_id = first.json()['pc_id']

        second = await client.post(
            '/api/webrtc/offer',
            json={
                'sdp': retry.localDescription.sdp,
                'type': retry.localDescription.type,
                'pc_id': old_pc_id,
                'restart_pc': True,
            },
        )
        assert second.status_code == 200, second.text
        new_pc_id = second.json()['pc_id']
        assert new_pc_id != old_pc_id

        session_service = application_container.webrtc_session_service()
        assert session_service.active_sessions == 1
        record = session_service.room_service.get_room(room['room_id'])
        assert record['pc_id'] == new_pc_id

        patch = await client.patch(
            '/api/webrtc/offer',
            json={
                'pc_id': new_pc_id,
                'candidates': [
                    {
                        'candidate': 'candidate:1 1 UDP 1 127.0.0.1 9 typ host',
                        'sdp_mid': '0',
                        'sdp_mline_index': 0,
                    }
                ],
            },
        )
        assert patch.status_code == 200, patch.text
    finally:
        await pc.close()
        await retry.close()
