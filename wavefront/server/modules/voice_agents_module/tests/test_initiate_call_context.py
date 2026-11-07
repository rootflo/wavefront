"""Outbound call context: the start-call payload and the call_processing prepare client.

Made-up scenario: a water utility CRM that starts a call about an overdue bill.
"""

import json
import uuid
from unittest.mock import AsyncMock, Mock

import flo_lib.http as httpx
import pytest
from pydantic import ValidationError

from common_module.response_formatter import ResponseFormatter
from voice_agents_module.controllers.voice_agent_controller import initiate_call
from voice_agents_module.models.voice_agent_schemas import (
    MAX_CALL_CONTEXT_BYTES,
    InitiateCallPayload,
)
from voice_agents_module.services.call_prepare_client import CallPrepareClient

AGENT_ID = uuid.uuid4()
PHONE = '+911234567890'


@pytest.fixture
def transport(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list = []
        timeouts: list = []
        handler = staticmethod(lambda request: httpx.Response(202, json={}))

    def dispatch(request):
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.handler(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        Recorder.timeouts = [*Recorder.timeouts, kwargs.get('timeout')]
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    Recorder.timeouts = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


def make_client(**overrides) -> CallPrepareClient:
    params = {
        'call_processing_base_url': 'http://call-processing:8004/',
        'passthrough_secret': 's3cret',
    }
    params.update(overrides)
    return CallPrepareClient(**params)


class TestInitiateCallPayload:
    def test_context_is_optional(self):
        assert InitiateCallPayload(to_number=PHONE).context is None

    def test_accepts_flat_text_context(self):
        payload = InitiateCallPayload(
            to_number=PHONE, context={'reason_for_call': 'overdue bill'}
        )
        assert payload.context == {'reason_for_call': 'overdue bill'}

    def test_size_counts_utf8_bytes(self):
        # 600 Devanagari characters: 1,800 UTF-8 bytes, but 3,600 as \u escapes
        context = {'notes': 'क' * 600}
        assert InitiateCallPayload(to_number=PHONE, context=context).context == context

    @pytest.mark.parametrize(
        'context',
        [
            {'Reason For Call': 'overdue bill'},  # key format
            {'notes': 'x' * (MAX_CALL_CONTEXT_BYTES + 1)},  # too big
            {'account': {'id': 'W-42'}},  # values are text only
        ],
    )
    def test_rejects_bad_context(self, context):
        with pytest.raises(ValidationError):
            InitiateCallPayload(to_number=PHONE, context=context)


class TestCallPrepareClient:
    async def test_sends_the_ringing_call_with_its_context(self, transport):
        ok = await make_client().prepare(
            AGENT_ID, 'CA123', PHONE, {'reason_for_call': 'overdue bill'}
        )

        assert ok is True
        [request] = transport.requests
        assert str(request.url) == 'http://call-processing:8004/api/calls/prepare'
        assert request.headers['X-Passthrough'] == 's3cret'
        assert json.loads(request.content) == {
            'agent_id': str(AGENT_ID),
            'call_ref': 'CA123',
            'customer_number': PHONE,
            'context': {'reason_for_call': 'overdue bill'},
        }
        assert transport.timeouts == [1.0]

    async def test_without_context_still_prepares_the_lookups(self, transport):
        assert await make_client().prepare(AGENT_ID, 'CA123', PHONE) is True
        assert json.loads(transport.requests[0].content)['context'] == {}

    async def test_no_passthrough_header_without_a_secret(self, transport):
        await make_client(passthrough_secret=None).prepare(AGENT_ID, 'CA123', PHONE)
        assert 'X-Passthrough' not in transport.requests[0].headers

    @pytest.mark.parametrize('call_ref', ['', 'unknown'])
    async def test_skips_calls_without_a_provider_id(self, transport, call_ref):
        assert await make_client().prepare(AGENT_ID, call_ref, PHONE) is False
        assert transport.requests == []

    async def test_skips_when_call_processing_is_not_configured(self, transport):
        client = make_client(call_processing_base_url=None)
        assert await client.prepare(AGENT_ID, 'CA123', PHONE) is False
        assert transport.requests == []

    async def test_a_rejection_never_raises(self, transport):
        transport.handler = staticmethod(lambda request: httpx.Response(401))
        assert await make_client().prepare(AGENT_ID, 'CA123', PHONE) is False

    async def test_a_network_error_never_raises(self, transport):
        def fail(request):
            raise httpx.ConnectError('call_processing is down', request=request)

        transport.handler = staticmethod(fail)
        assert await make_client().prepare(AGENT_ID, 'CA123', PHONE) is False


class TestInitiateCall:
    async def test_dials_first_then_prepares_with_the_provider_call_id(self):
        order = []
        voice_agent_service = Mock()
        voice_agent_service.get_agent = AsyncMock(
            return_value={
                'status': 'active',
                'outbound_numbers': ['+911100000000'],
                'telephony_config_id': 'tel-1',
            }
        )
        voice_agent_service.telephony_config_service.get_config = AsyncMock(
            return_value={
                'provider': 'twilio',
                'credentials': {'account_sid': 'AC1', 'auth_token': 't'},
            }
        )
        twilio_service = Mock()
        twilio_service.initiate_call = Mock(
            side_effect=lambda **kw: order.append('dial')
            or {
                'call_sid': 'CA123',
                'status': 'queued',
                'to_number': PHONE,
                'from_number': '+911100000000',
            }
        )
        prepare_client = Mock()
        prepare_client.prepare = AsyncMock(
            side_effect=lambda **kw: order.append('prepare') or False
        )

        response = await initiate_call(
            agent_id=AGENT_ID,
            payload=InitiateCallPayload(
                to_number=PHONE, context={'reason_for_call': 'overdue bill'}
            ),
            response_formatter=ResponseFormatter(),
            voice_agent_service=voice_agent_service,
            twilio_service=twilio_service,
            exotel_service=Mock(),
            smartflo_service=Mock(),
            call_prepare_client=prepare_client,
        )

        # A failed prepare (False) still returns the placed call
        assert response.status_code == 201
        assert order == ['dial', 'prepare']
        prepare_client.prepare.assert_awaited_once_with(
            agent_id=AGENT_ID,
            call_ref='CA123',
            customer_number=PHONE,
            context={'reason_for_call': 'overdue bill'},
        )
