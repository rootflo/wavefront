"""The send-message route for an agent-backed session: JSON and SSE shapes."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from flo_ai.agent import Agent

from chatbots_module.controllers.chat_session_controller import (
    _send_agent_message,
    _stream_agent_reply,
)
from chatbots_module.services.agent_chat_service import (
    AgentChatError,
    AgentChatService,
)
from chatbots_module.utils.auth_utils import caller_credentials
from chatbots_module.utils.constants import (
    AGENT_UNAVAILABLE_MESSAGE,
    MODEL_REFUSED_MESSAGE,
)

from agent_fakes import InMemoryChatStore, ScriptedLLM, order_tool, text, tool_call
from flo_ai.models import ModelRefusedError


class Formatter:
    def buildSuccessResponse(self, data):
        return {'data': data}

    def buildErrorResponse(self, message):
        return {'error': message}


def _request(headers=None):
    return SimpleNamespace(headers=headers or {'Authorization': 'Bearer user-token'})


def _setup(responses, build_error=None):
    store = InMemoryChatStore()
    store.ensure_title = AsyncMock()
    # The route serialises the stored user message.
    original_add = store.add_message

    async def add_message(**kwargs):
        row = await original_add(**kwargs)
        row.to_dict = lambda: {
            'id': str(row.id),
            'role': row.role,
            'content': row.content,
        }
        return row

    store.add_message = add_message

    service = AgentChatService(
        chat_session_service=store,
        chat_message_repository=store,
        agent_crud_service=AsyncMock(),
        agent_inference_service=AsyncMock(),
    )
    agent = Agent(
        'support',
        'You help with orders.',
        ScriptedLLM(responses),
        tools=[order_tool()],
        interactive=True,
    )
    service.build_agent = AsyncMock(return_value=agent, side_effect=build_error)
    session = SimpleNamespace(
        id=uuid.uuid4(),
        metadata_={'agent_id': str(uuid.uuid4()), 'agent_version': 1},
    )
    return store, service, session


async def _send(store, service, session, stream=False, request=None):
    return await _send_agent_message(
        request=request or _request(),
        session=session,
        content='where is A-1?',
        stream=stream,
        response_formatter=Formatter(),
        chat_session_service=store,
        agent_chat_service=service,
    )


class TestJsonReply:
    async def test_reply_and_steps(self):
        store, service, session = _setup(
            [tool_call('get_order_status', order_id='A-1'), text('It shipped.')]
        )

        response = await _send(store, service, session)

        assert response.status_code == 201
        data = json.loads(response.body)['data']
        assert data['user_message']['content'] == 'where is A-1?'
        assert data['assistant_message']['content'] == 'It shipped.'
        assert data['assistant_message']['role'] == 'assistant'
        assert data['assistant_message']['id'] == str(store.rows[-1].id)
        assert [step['type'] for step in data['steps']] == ['tool_call', 'tool_result']
        store.ensure_title.assert_awaited_once()

    async def test_the_agent_is_built_with_the_callers_credentials(self):
        store, service, session = _setup([text('hello')])

        await _send(store, service, session)

        service.build_agent.assert_awaited_once_with(
            session, access_token='user-token', app_key=None
        )

    async def test_an_unavailable_agent_is_a_conflict_and_writes_nothing(self):
        store, service, session = _setup([], build_error=AgentChatError('gone'))

        response = await _send(store, service, session)

        assert response.status_code == 409
        assert json.loads(response.body) == {'error': AGENT_UNAVAILABLE_MESSAGE}
        assert store.rows == []

    async def test_a_declined_turn_is_an_error_response(self):
        store, service, session = _setup([ModelRefusedError('declined')])

        response = await _send(store, service, session)

        assert response.status_code == 502
        assert json.loads(response.body) == {'error': MODEL_REFUSED_MESSAGE}
        # The user's message is kept, as on the other path.
        assert [row.role for row in store.rows] == ['user']


class TestStreamedReply:
    async def test_frames_are_sent_as_sse(self):
        store, service, session = _setup(
            [tool_call('get_order_status', order_id='A-1'), text('It shipped.')]
        )

        response = await _send(store, service, session, stream=True)
        chunks = [chunk async for chunk in response.body_iterator]

        assert response.media_type == 'text/event-stream'
        assert all(
            chunk.startswith('data: ') and chunk.endswith('\n\n') for chunk in chunks
        )
        frames = [json.loads(chunk[len('data: ') :]) for chunk in chunks]
        assert [frame.get('type') for frame in frames] == [
            'tool_call',
            'tool_result',
            'message',
            None,
        ]
        assert frames[-1]['done'] is True
        assert frames[-1]['message_id'] == frames[2]['message_id']

    async def test_relay_serialises_whatever_the_frames_carry(self):
        async def frames():
            yield {'type': 'tool_call', 'arguments': {'id': uuid.UUID(int=1)}}

        (chunk,) = [chunk async for chunk in _stream_agent_reply(frames())]

        assert json.loads(chunk[len('data: ') :])['arguments']['id'] == str(
            uuid.UUID(int=1)
        )


class TestCallerCredentials:
    def test_bearer_token_and_app_key(self):
        from user_management_module.constants.auth import RootfloHeaders

        request = _request(
            {'Authorization': 'Bearer abc', RootfloHeaders.CLIENT_KEY: 'app-1'}
        )
        assert caller_credentials(request) == ('abc', 'app-1')

    def test_no_credentials(self):
        assert caller_credentials(_request({'X-Other': '1'})) == (None, None)

    def test_a_non_bearer_header_is_not_a_token(self):
        request = _request({'Authorization': 'Basic abc'})
        assert caller_credentials(request) == (None, None)
