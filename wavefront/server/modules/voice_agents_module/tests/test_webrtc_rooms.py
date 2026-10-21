"""Create-room endpoint and the call_processing client behind it (no network)."""

import json
import uuid
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import flo_lib.http as httpx
import pytest

from common_module.response_formatter import ResponseFormatter
from voice_agents_module.controllers.voice_agent_controller import (
    MAX_ROOM_SWITCHABLE_AGENTS,
    create_webrtc_room,
    proxy_webrtc_ice_candidates,
    proxy_webrtc_offer,
)
from voice_agents_module.models.voice_agent_schemas import CreateWebRTCRoomPayload
from voice_agents_module.services.webrtc_room_client import (
    FLOWARE_SIGNALING_PATH,
    WebRTCRoomClient,
    WebRTCRoomClientError,
)

AGENT_ID = uuid.uuid4()
CALL_PROCESSING_ROOM = {
    'room_id': 'room-1',
    'voice_agent_id': str(AGENT_ID),
    'join_token': 'one-time-token',
    'signaling_url': 'https://calls.example.com/api/webrtc',
}


@pytest.fixture
def transport(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        handler = staticmethod(
            lambda request: httpx.Response(201, json=CALL_PROCESSING_ROOM)
        )

    def dispatch(request: httpx.Request) -> httpx.Response:
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.handler(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


def make_client(**overrides) -> WebRTCRoomClient:
    params = {
        'call_processing_base_url': 'http://call-processing:8004/',
        'passthrough_secret': 's3cret',
        'signaling_via_floware': False,
    }
    params.update(overrides)
    return WebRTCRoomClient(**params)


class TestWebRTCRoomClient:
    async def test_create_room_uses_passthrough_and_returns_public_signaling_url(
        self, transport
    ):
        room = await make_client().create_room(AGENT_ID)

        (request,) = transport.requests
        assert str(request.url) == 'http://call-processing:8004/api/webrtc/rooms'
        assert request.headers['X-Passthrough'] == 's3cret'
        assert json.loads(request.content) == {'voice_agent_id': str(AGENT_ID)}
        assert room['join_token'] == 'one-time-token'
        assert room['signaling_url'] == 'https://calls.example.com/api/webrtc'
        assert room['signaling_via_floware'] is False

    async def test_create_room_forwards_the_swap_allowlist(self, transport):
        other = uuid.uuid4()
        await make_client().create_room(AGENT_ID, allowed_agent_ids=[AGENT_ID, other])

        (request,) = transport.requests
        assert json.loads(request.content) == {
            'voice_agent_id': str(AGENT_ID),
            'allowed_agent_ids': [str(AGENT_ID), str(other)],
        }

    async def test_create_room_sends_the_language_flag_only_when_true(self, transport):
        await make_client().create_room(AGENT_ID, room_context_handles_language=True)
        await make_client().create_room(AGENT_ID, room_context_handles_language=False)

        first, second = transport.requests
        assert json.loads(first.content) == {
            'voice_agent_id': str(AGENT_ID),
            'room_context_handles_language': True,
        }
        assert json.loads(second.content) == {'voice_agent_id': str(AGENT_ID)}

    async def test_create_room_sends_the_history_flag_only_when_false(self, transport):
        await make_client().create_room(AGENT_ID, carry_history_on_swap=False)
        await make_client().create_room(AGENT_ID, carry_history_on_swap=True)

        first, second = transport.requests
        assert json.loads(first.content) == {
            'voice_agent_id': str(AGENT_ID),
            'carry_history_on_swap': False,
        }
        assert json.loads(second.content) == {'voice_agent_id': str(AGENT_ID)}

    async def test_create_room_points_browser_at_floware_when_proxying(self, transport):
        room = await make_client(signaling_via_floware=True).create_room(AGENT_ID)

        assert room['signaling_url'] == FLOWARE_SIGNALING_PATH
        assert room['signaling_via_floware'] is True

    async def test_create_room_failure_is_a_bad_gateway(self, transport):
        transport.handler = lambda request: httpx.Response(500, text='boom')

        with pytest.raises(WebRTCRoomClientError) as exc_info:
            await make_client().create_room(AGENT_ID)

        assert exc_info.value.status_code == 502

    async def test_create_room_without_base_url_is_unavailable(self, transport):
        with pytest.raises(WebRTCRoomClientError) as exc_info:
            await make_client(call_processing_base_url=None).create_room(AGENT_ID)

        assert exc_info.value.status_code == 503
        assert transport.requests == []

    async def test_forward_signaling_is_disabled_by_default(self, transport):
        with pytest.raises(WebRTCRoomClientError) as exc_info:
            await make_client().forward_signaling('POST', b'{}', None)

        assert exc_info.value.status_code == 404
        assert transport.requests == []

    async def test_forward_signaling_passes_body_and_sticky_cookie_both_ways(
        self, transport
    ):
        transport.handler = lambda request: httpx.Response(
            409,
            json={'error': 'room_already_joined'},
            headers={'set-cookie': 'wf_webrtc_affinity=pod-a; Path=/'},
        )

        proxied = await make_client(signaling_via_floware=True).forward_signaling(
            'POST', b'{"sdp": "x"}', 'wf_webrtc_affinity=pod-a'
        )

        (request,) = transport.requests
        assert request.method == 'POST'
        assert str(request.url) == 'http://call-processing:8004/api/webrtc/offer'
        assert request.content == b'{"sdp": "x"}'
        assert request.headers['cookie'] == 'wf_webrtc_affinity=pod-a'
        assert 'x-passthrough' not in request.headers
        assert proxied.status_code == 409
        assert json.loads(proxied.content) == {'error': 'room_already_joined'}
        assert proxied.set_cookie == 'wf_webrtc_affinity=pod-a; Path=/'

    @pytest.mark.parametrize(
        'browser_cookie, expected',
        [
            (
                'session=secret; wf_webrtc_affinity=pod-a; theme=dark',
                'wf_webrtc_affinity=pod-a',
            ),
            ('session=secret; theme=dark', None),
            ('wf_webrtc_affinity=', None),
            (None, None),
        ],
    )
    async def test_forward_signaling_forwards_only_affinity_cookie(
        self, transport, browser_cookie, expected
    ):
        transport.handler = lambda request: httpx.Response(200, json={})

        await make_client(signaling_via_floware=True).forward_signaling(
            'POST', b'{}', browser_cookie
        )

        (request,) = transport.requests
        assert request.headers.get('cookie') == expected


def agent(status='active'):
    return {
        'id': str(AGENT_ID),
        'name': 'Alpha',
        'status': status,
        'outbound_numbers': [],
    }


def other_agent(name='Other', status='active', **extra):
    return {'id': str(uuid.uuid4()), 'name': name, 'status': status, **extra}


async def call_create(voice_agent_service, room_client, payload=None):
    return await create_webrtc_room(
        agent_id=AGENT_ID,
        payload=payload,
        response_formatter=ResponseFormatter(),
        voice_agent_service=voice_agent_service,
        webrtc_room_client=room_client,
    )


class TestCreateRoomEndpoint:
    async def test_active_agent_gets_a_room_without_outbound_numbers(self):
        room_client = Mock(create_room=AsyncMock(return_value=CALL_PROCESSING_ROOM))
        service = Mock(
            get_agent=AsyncMock(return_value=agent('active')),
            list_agents=AsyncMock(return_value=[agent('active')]),
        )

        response = await call_create(service, room_client)

        assert response.status_code == 201
        body = json.loads(response.body)
        assert body['data']['join_token'] == 'one-time-token'
        assert body['data']['room_id'] == 'room-1'
        room_client.create_room.assert_awaited_once_with(
            AGENT_ID,
            allowed_agent_ids=[AGENT_ID],
            room_context_handles_language=False,
            carry_history_on_swap=True,
        )
        assert body['data']['agents'] == [{'id': str(AGENT_ID), 'name': 'Alpha'}]

    async def test_unknown_agent_is_404(self):
        room_client = Mock(create_room=AsyncMock())
        service = Mock(get_agent=AsyncMock(return_value=None))

        response = await call_create(service, room_client)

        assert response.status_code == 404
        room_client.create_room.assert_not_awaited()

    async def test_inactive_agent_is_400(self):
        room_client = Mock(create_room=AsyncMock())
        service = Mock(get_agent=AsyncMock(return_value=agent('inactive')))

        response = await call_create(service, room_client)

        assert response.status_code == 400
        room_client.create_room.assert_not_awaited()

    async def test_call_processing_failure_is_surfaced(self):
        room_client = Mock(
            create_room=AsyncMock(
                side_effect=WebRTCRoomClientError('Voice service is unreachable', 502)
            )
        )
        service = Mock(
            get_agent=AsyncMock(return_value=agent('active')),
            list_agents=AsyncMock(return_value=[]),
        )

        response = await call_create(service, room_client)

        assert response.status_code == 502
        assert (
            json.loads(response.body)['meta']['error'] == 'Voice service is unreachable'
        )


class TestCreateRoomAllowlist:
    """The room's hot-swap allowlist is computed server-side from active agents."""

    async def _create(self, all_agents, payload=None):
        room_client = Mock(
            create_room=AsyncMock(return_value=dict(CALL_PROCESSING_ROOM))
        )
        service = Mock(
            get_agent=AsyncMock(return_value=agent('active')),
            list_agents=AsyncMock(return_value=all_agents),
        )
        response = await call_create(service, room_client, payload)
        assert response.status_code == 201
        return room_client, json.loads(response.body)['data']

    async def test_only_active_non_deleted_agents_are_allowed_initial_first(self):
        beta = other_agent('Beta')
        gamma = other_agent('Gamma')
        room_client, data = await self._create(
            [
                other_agent('Inactive', status='inactive'),
                other_agent('Deleted', is_deleted=True),
                beta,
                agent('active'),  # the initial agent is not duplicated
                gamma,
            ]
        )

        expected = [
            {'id': str(AGENT_ID), 'name': 'Alpha'},
            {'id': beta['id'], 'name': 'Beta'},
            {'id': gamma['id'], 'name': 'Gamma'},
        ]
        assert data['agents'] == expected
        assert room_client.create_room.await_args.kwargs['allowed_agent_ids'] == [
            UUID(a['id']) for a in expected
        ]

    async def test_request_body_can_only_narrow_the_allowlist(self):
        beta = other_agent('Beta')
        gamma = other_agent('Gamma')
        stranger = uuid.uuid4()  # not an agent of this app
        _, data = await self._create(
            [beta, gamma],
            CreateWebRTCRoomPayload(allowed_agent_ids=[UUID(beta['id']), stranger]),
        )

        assert [a['id'] for a in data['agents']] == [str(AGENT_ID), beta['id']]

    async def test_language_flag_defaults_to_native_and_is_forwarded_when_set(self):
        room_client, _ = await self._create([])
        assert (
            room_client.create_room.await_args.kwargs['room_context_handles_language']
            is False
        )

        room_client, _ = await self._create(
            [], CreateWebRTCRoomPayload(room_context_handles_language=True)
        )
        assert (
            room_client.create_room.await_args.kwargs['room_context_handles_language']
            is True
        )

    async def test_history_flag_defaults_to_carrying_and_is_forwarded_when_off(self):
        room_client, _ = await self._create([])
        assert (
            room_client.create_room.await_args.kwargs['carry_history_on_swap'] is True
        )

        room_client, _ = await self._create(
            [], CreateWebRTCRoomPayload(carry_history_on_swap=False)
        )
        assert (
            room_client.create_room.await_args.kwargs['carry_history_on_swap'] is False
        )

    async def test_allowlist_is_capped(self):
        many = [other_agent(f'A{i}') for i in range(MAX_ROOM_SWITCHABLE_AGENTS + 10)]
        room_client, data = await self._create(many)

        assert len(data['agents']) == MAX_ROOM_SWITCHABLE_AGENTS
        assert data['agents'][0]['id'] == str(AGENT_ID)
        assert (
            len(room_client.create_room.await_args.kwargs['allowed_agent_ids'])
            == MAX_ROOM_SWITCHABLE_AGENTS
        )


class TestSignalingProxyEndpoints:
    @pytest.mark.parametrize(
        'handler, method',
        [(proxy_webrtc_offer, 'POST'), (proxy_webrtc_ice_candidates, 'PATCH')],
    )
    async def test_proxy_returns_call_processing_response_and_cookie(
        self, handler, method
    ):
        request = Mock(
            body=AsyncMock(return_value=b'{"pc_id": "pc"}'),
            headers={'cookie': 'wf_webrtc_affinity=pod-a'},
        )
        room_client = Mock(
            forward_signaling=AsyncMock(
                return_value=Mock(
                    status_code=200,
                    content=b'{"sdp": "answer"}',
                    media_type='application/json',
                    set_cookie='wf_webrtc_affinity=pod-a',
                )
            )
        )

        response = await handler(
            request=request,
            response_formatter=ResponseFormatter(),
            webrtc_room_client=room_client,
        )

        room_client.forward_signaling.assert_awaited_once_with(
            method, b'{"pc_id": "pc"}', 'wf_webrtc_affinity=pod-a'
        )
        assert response.status_code == 200
        assert response.body == b'{"sdp": "answer"}'
        assert response.headers['set-cookie'] == 'wf_webrtc_affinity=pod-a'

    async def test_proxy_disabled_is_404(self):
        request = Mock(body=AsyncMock(return_value=b'{}'), headers={})

        response = await proxy_webrtc_offer(
            request=request,
            response_formatter=ResponseFormatter(),
            webrtc_room_client=make_client(signaling_via_floware=False),
        )

        assert response.status_code == 404
