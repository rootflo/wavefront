"""An agent-backed chat turn: what is stored, what is streamed, what is replayed."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flo_ai.agent import Agent, AgentEvent, AgentEventType
from flo_ai.llm.guarded_llm import GuardrailBlocked
from flo_ai.models import (
    AssistantMessage,
    FunctionMessage,
    ModelRefusedError,
    ToolCall,
    UserMessage,
)

from chatbots_module.services.agent_chat_service import (
    AgentChatError,
    AgentChatService,
)
from chatbots_module.utils.constants import (
    BLOCKED_BY_POLICY_MESSAGE,
    MODEL_FAILURE_MESSAGE,
    MODEL_REFUSED_MESSAGE,
    TURN_NOT_SAVED_MESSAGE,
)

from agent_fakes import InMemoryChatStore, ScriptedLLM, order_tool, text, tool_call


def _session(agent_version=3):
    return SimpleNamespace(
        id=uuid.uuid4(),
        metadata_={'agent_id': str(uuid.uuid4()), 'agent_version': agent_version},
    )


def _service(store=None, crud=None, inference=None):
    store = store or InMemoryChatStore()
    return AgentChatService(
        chat_session_service=store,
        chat_message_repository=store,
        agent_crud_service=crud or AsyncMock(),
        agent_inference_service=inference or AsyncMock(),
    )


def _agent(responses, lookups=None, fail=False):
    return Agent(
        'support',
        'You help with orders.',
        ScriptedLLM(responses),
        tools=[order_tool(lookups, fail=fail)],
        interactive=True,
    )


async def _send(service, store, agent, session, user_text):
    """What the controller does for one turn; returns the frames."""
    await store.add_message(session.id, 'user', user_text)
    history = await service.load_history(session.id)
    return [frame async for frame in service.run_turn(agent, session, history)]


def _row(role, content, metadata=None):
    return SimpleNamespace(
        id=uuid.uuid4(), role=role, content=content, metadata_=metadata
    )


class TestWhichSessions:
    def test_a_session_pinned_to_an_agent_takes_the_agent_path(self):
        assert AgentChatService.is_agent_session(_session()) is True

    @pytest.mark.parametrize('metadata', [None, {}, {'other': 1}])
    def test_any_other_session_does_not(self, metadata):
        session = SimpleNamespace(metadata_=metadata)
        assert AgentChatService.is_agent_session(session) is False


class TestPin:
    async def test_follows_the_agents_current_version_when_not_pinned(self):
        crud = AsyncMock()
        crud.get_agent.return_value = {'version': 7}
        chatbot = SimpleNamespace(agent_id=uuid.uuid4(), agent_version=None)

        pinned = await _service(crud=crud).pin(chatbot)

        assert pinned == {'agent_id': str(chatbot.agent_id), 'agent_version': 7}
        crud.get_agent.assert_awaited_once_with(chatbot.agent_id, version=None)

    async def test_keeps_the_chatbots_pinned_version(self):
        crud = AsyncMock()
        crud.get_agent.return_value = {'version': 2}
        chatbot = SimpleNamespace(agent_id=uuid.uuid4(), agent_version=2)

        pinned = await _service(crud=crud).pin(chatbot)

        assert pinned['agent_version'] == 2
        crud.get_agent.assert_awaited_once_with(chatbot.agent_id, version=2)

    async def test_a_missing_agent_is_reported(self):
        crud = AsyncMock()
        crud.get_agent.side_effect = ValueError('Agent not found')
        chatbot = SimpleNamespace(agent_id=uuid.uuid4(), agent_version=None)

        with pytest.raises(AgentChatError):
            await _service(crud=crud).pin(chatbot)


class TestBuildAgent:
    async def test_builds_the_pinned_version_with_the_callers_credentials(self):
        session = _session(agent_version=3)
        crud = AsyncMock()
        crud.get_agent.return_value = {
            'yaml_content': 'agent: {}',
            'name': 'support',
            'namespace': 'acme',
        }
        built = SimpleNamespace(interactive=False)
        inference = AsyncMock()
        inference.create_agent_from_yaml.return_value = built

        agent = await _service(crud=crud, inference=inference).build_agent(
            session, access_token='user-token', app_key='app-key'
        )

        crud.get_agent.assert_awaited_once_with(
            uuid.UUID(session.metadata_['agent_id']), version=3
        )
        inference.create_agent_from_yaml.assert_awaited_once_with(
            'agent: {}',
            'support',
            access_token='user-token',
            app_key='app-key',
            namespace='acme',
        )
        assert agent is built
        assert agent.interactive is True

    async def test_a_failure_does_not_leak_its_cause(self):
        crud = AsyncMock()
        crud.get_agent.side_effect = ValueError('bucket internal-host/agents missing')

        with pytest.raises(AgentChatError) as raised:
            await _service(crud=crud).build_agent(_session())

        assert 'internal-host' not in str(raised.value)


class TestRowsToMessages:
    def test_a_stored_turn_becomes_the_agents_conversation(self):
        rows = [
            _row('user', 'where is A-1?'),
            _row(
                'assistant',
                'Checking.',
                {
                    'tool_calls': [
                        {
                            'id': 'toolu_1',
                            'name': 'get_order_status',
                            'arguments': {'order_id': 'A-1'},
                        }
                    ]
                },
            ),
            _row(
                'tool',
                'A-1 shipped',
                {'name': 'get_order_status', 'tool_call_id': 'toolu_1'},
            ),
            _row('assistant', 'It shipped.'),
        ]

        messages = AgentChatService.to_agent_messages(rows)

        assert messages == [
            UserMessage(content='where is A-1?'),
            AssistantMessage(
                content='Checking.',
                tool_calls=[
                    ToolCall(
                        name='get_order_status',
                        arguments={'order_id': 'A-1'},
                        id='toolu_1',
                    )
                ],
            ),
            FunctionMessage(
                content='A-1 shipped', name='get_order_status', tool_call_id='toolu_1'
            ),
            AssistantMessage(content='It shipped.'),
        ]

    def test_rows_from_a_prompt_based_chatbot_are_valid_too(self):
        rows = [
            _row('assistant', 'Welcome!'),
            _row('user', 'hi'),
            _row('assistant', 'hello'),
        ]

        messages = AgentChatService.to_agent_messages(rows)

        # The window opens on a user message, so the welcome line is dropped.
        assert messages == [
            UserMessage(content='hi'),
            AssistantMessage(content='hello'),
        ]

    def test_a_window_that_opens_mid_turn_is_moved_to_the_next_user_message(self):
        rows = [
            _row('tool', 'A-1 shipped', {'name': 'get_order_status'}),
            _row('assistant', 'It shipped.'),
            _row('user', 'thanks'),
            _row('assistant', 'Any time.'),
        ]

        messages = AgentChatService.to_agent_messages(rows)

        assert messages == [
            UserMessage(content='thanks'),
            AssistantMessage(content='Any time.'),
        ]

    def test_notes_the_agent_wrote_to_itself_are_not_replayed(self):
        rows = [
            _row('user', 'hi'),
            _row('assistant', 'Error occurred. Analysis: ...', {'notice': True}),
            _row('user', 'keep going', {'notice': True}),
            _row('assistant', 'hello'),
        ]

        messages = AgentChatService.to_agent_messages(rows)

        assert messages == [
            UserMessage(content='hi'),
            AssistantMessage(content='hello'),
        ]

    def test_no_user_message_in_the_window_gives_nothing(self):
        assert AgentChatService.to_agent_messages([_row('assistant', 'hi')]) == []


class TestEventsToRows:
    def _event(self, event_type, message, is_final=False):
        return AgentEvent(
            type=event_type, agent='support', message=message, is_final=is_final
        )

    def test_tool_call(self):
        message = AssistantMessage(
            content='',
            tool_calls=[ToolCall(name='lookup', arguments={'q': 1}, id='toolu_1')],
        )

        row = AgentChatService.to_row(self._event(AgentEventType.TOOL_CALL, message))

        assert row == (
            'assistant',
            '',
            {
                'tool_calls': [
                    {'id': 'toolu_1', 'name': 'lookup', 'arguments': {'q': 1}}
                ]
            },
        )

    def test_tool_result(self):
        message = FunctionMessage(content='42', name='lookup', tool_call_id='toolu_1')

        row = AgentChatService.to_row(self._event(AgentEventType.TOOL_RESULT, message))

        assert row == ('tool', '42', {'name': 'lookup', 'tool_call_id': 'toolu_1'})

    def test_final_reply_has_no_metadata(self):
        event = self._event(
            AgentEventType.MESSAGE, AssistantMessage(content='Done.'), is_final=True
        )

        assert AgentChatService.to_row(event) == ('assistant', 'Done.', None)

    def test_a_notice_keeps_its_role_and_is_marked(self):
        nudge = self._event(AgentEventType.NOTICE, UserMessage(content='keep going'))
        analysis = self._event(
            AgentEventType.NOTICE, AssistantMessage(content='Error occurred.')
        )

        assert AgentChatService.to_row(nudge) == (
            'user',
            'keep going',
            {'notice': True},
        )
        assert AgentChatService.to_row(analysis) == (
            'assistant',
            'Error occurred.',
            {'notice': True},
        )


class TestTurn:
    async def test_each_step_is_stored_and_streamed_in_order(self):
        store = InMemoryChatStore()
        service = _service(store)
        session = _session()
        lookups = []
        agent = _agent(
            [
                tool_call('get_order_status', 'toolu_1', order_id='A-1'),
                text('It shipped.'),
            ],
            lookups,
        )

        frames = await _send(service, store, agent, session, 'where is A-1?')

        assert lookups == ['A-1']
        assert [frame.get('type') for frame in frames] == [
            'tool_call',
            'tool_result',
            'message',
            None,
        ]
        assert frames[0]['name'] == 'get_order_status'
        assert frames[0]['arguments'] == {'order_id': 'A-1'}
        assert frames[1]['name'] == 'get_order_status'
        assert 'A-1 shipped' in frames[1]['content']
        assert frames[2]['content'] == 'It shipped.'
        assert frames[2]['final'] is True
        assert frames[3] == {'done': True, 'message_id': frames[2]['message_id']}

        roles = [row.role for row in store.rows]
        assert roles == ['user', 'assistant', 'tool', 'assistant']
        assert store.rows[1].metadata_['tool_calls'][0]['arguments'] == {
            'order_id': 'A-1'
        }
        assert store.rows[2].metadata_ == {
            'name': 'get_order_status',
            'tool_call_id': 'toolu_1',
        }
        assert store.rows[3].metadata_ is None
        # Every step frame names the row it was stored as.
        assert [frame['message_id'] for frame in frames[:3]] == [
            str(row.id) for row in store.rows[1:]
        ]

    async def test_the_next_turn_is_given_the_earlier_tool_call(self):
        store = InMemoryChatStore()
        service = _service(store)
        session = _session()
        first = _agent(
            [tool_call('get_order_status', order_id='A-1'), text('It shipped.')]
        )
        await _send(service, store, first, session, 'where is A-1?')

        # A fresh agent, as on the next request.
        second = _agent([text('Order A-1.')])
        frames = await _send(service, store, second, session, 'which order was that?')

        assert frames[-2]['content'] == 'Order A-1.'
        request = second.llm.requests[0]
        assert [message['role'] for message in request] == [
            'system',
            'user',
            'assistant',
            'function',
            'assistant',
            'user',
        ]
        assert request[2]['call'] == ('get_order_status', {'order_id': 'A-1'})

    async def test_a_question_from_the_agent_is_its_reply(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent([text('Which order do you mean?')])

        frames = await _send(service, store, agent, _session(), 'where is my order?')

        assert [frame.get('type') for frame in frames] == ['message', None]
        assert frames[0]['content'] == 'Which order do you mean?'
        # One model call: the question was not treated as unfinished work.
        assert len(agent.llm.requests) == 1

    async def test_angle_brackets_in_a_message_are_just_text(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent([text('Use <workflow_name>.'), text('Yes.')])
        session = _session()

        await _send(service, store, agent, session, 'what goes in <name>?')
        agent.clear_history()
        frames = await _send(service, store, agent, session, 'is that right?')

        assert frames[-1].get('done') is True

    async def test_a_blocked_turn_keeps_only_the_users_message(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent(
            [
                tool_call('get_order_status', order_id='A-1'),
                GuardrailBlocked('blocked'),
            ]
        )

        frames = await _send(service, store, agent, _session(), 'where is A-1?')

        assert frames[-1] == {'error': BLOCKED_BY_POLICY_MESSAGE}
        assert [row.role for row in store.rows] == ['user']
        assert len(store.deleted) == 2

    async def test_a_refused_turn_keeps_only_the_users_message(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent([ModelRefusedError('declined', category='cyber')])

        frames = await _send(service, store, agent, _session(), 'do something bad')

        assert frames == [{'error': MODEL_REFUSED_MESSAGE}]
        assert [row.role for row in store.rows] == ['user']

    async def test_a_failed_turn_keeps_its_steps_and_hides_the_cause(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent(
            [
                tool_call('get_order_status', order_id='A-1'),
                RuntimeError('https://internal-gateway/v1 timed out'),
                # flo-ai asks the model to analyse the error before giving up.
                text('This is not recoverable.'),
            ]
        )

        frames = await _send(service, store, agent, _session(), 'where is A-1?')

        assert frames[-1] == {'error': MODEL_FAILURE_MESSAGE}
        assert 'internal-gateway' not in str(frames)
        # The call and its result are a valid conversation to continue from.
        assert [row.role for row in store.rows] == ['user', 'assistant', 'tool']

    async def test_a_failing_tool_is_stored_as_its_result(self):
        store = InMemoryChatStore()
        service = _service(store)
        agent = _agent(
            [
                tool_call('get_order_status', order_id='A-1'),
                text('This is not recoverable.'),
            ],
            fail=True,
        )

        frames = await _send(service, store, agent, _session(), 'where is A-1?')

        assert frames[-1] == {'error': MODEL_FAILURE_MESSAGE}
        assert [row.role for row in store.rows] == ['user', 'assistant', 'tool']
        assert store.rows[2].content.startswith('Tool execution error')

    async def test_a_step_that_cannot_be_stored_stops_the_turn(self):
        # Add 1 is the user's message, add 2 the tool call, add 3 the result.
        store = InMemoryChatStore(fail_on_add=3)
        service = _service(store)
        agent = _agent(
            [tool_call('get_order_status', order_id='A-1'), text('It shipped.')]
        )

        frames = await _send(service, store, agent, _session(), 'where is A-1?')

        assert frames[-1] == {'error': TURN_NOT_SAVED_MESSAGE}
        # The agent was not asked for a reply it could not have stored.
        assert len(agent.llm.requests) == 1
        assert [row.role for row in store.rows] == ['user', 'assistant']

    async def test_a_turn_finishes_after_the_client_hangs_up(self):
        store = InMemoryChatStore()
        service = _service(store)
        session = _session()
        agent = _agent(
            [tool_call('get_order_status', order_id='A-1'), text('It shipped.')]
        )
        await store.add_message(session.id, 'user', 'where is A-1?')
        history = await service.load_history(session.id)

        frames = service.run_turn(agent, session, history)
        first = await frames.__anext__()
        await frames.aclose()  # the client is gone

        assert first['type'] == 'tool_call'
        await asyncio.gather(*service._turns)
        assert [row.role for row in store.rows] == [
            'user',
            'assistant',
            'tool',
            'assistant',
        ]
        assert store.rows[-1].content == 'It shipped.'
