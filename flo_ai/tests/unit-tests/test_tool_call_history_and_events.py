"""Tests for tool calls kept as messages, and the events an agent reports per step."""

from unittest.mock import MagicMock

import pytest

from flo_ai.agent import Agent, AgentEventType, ReasoningPattern
from flo_ai.llm import Anthropic, OpenAI
from flo_ai.llm.guarded_llm import GuardedLLM
from flo_ai.models import (
    AssistantMessage,
    FunctionMessage,
    SystemMessage,
    ToolCall,
    UserMessage,
)
from flo_ai.models.agent_error import AgentError
from flo_ai.tool import Tool

from test_plan_execute import ScriptedLLM, call, plan, text


class CallAwareLLM(ScriptedLLM):
    """A provider whose message format has a place for the tool call."""

    def format_tool_call_message(self, content, tool_calls):
        return {
            'role': 'assistant',
            'content': content or None,
            'call': (tool_calls[0].name, tool_calls[0].arguments, tool_calls[0].id),
        }


def create_tool(fail=False):
    async def create_workflow(title: str) -> str:
        if fail:
            raise RuntimeError('quota exceeded')
        return f'created {title}'

    return Tool(
        name='create_workflow',
        description='Create a workflow',
        function=create_workflow,
        parameters={'title': {'type': 'string', 'description': 'Workflow name'}},
    )


def call_with_id(name, call_id, **arguments):
    return {'call': {'name': name, 'arguments': arguments, 'id': call_id}}


STORED_TURN = [
    UserMessage(content='make a workflow'),
    AssistantMessage(
        content='On it.',
        tool_calls=[
            ToolCall(name='create_workflow', arguments={'title': 'w1'}, id='toolu_1')
        ],
    ),
    FunctionMessage(
        content='created w1', name='create_workflow', tool_call_id='toolu_1'
    ),
    AssistantMessage(content='Done.'),
]


class TestToolCallsInHistory:
    async def test_the_call_is_recorded_before_its_result(self):
        llm = ScriptedLLM(
            [
                call_with_id('create_workflow', 'toolu_1', title='w1'),
                text('Done'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        history = await agent.run('make a workflow')

        call_message, result_message = history[2], history[3]
        assert isinstance(call_message, AssistantMessage)
        assert call_message.tool_calls == [
            ToolCall(name='create_workflow', arguments={'title': 'w1'}, id='toolu_1')
        ]
        assert isinstance(result_message, FunctionMessage)
        assert result_message.name == 'create_workflow'
        assert result_message.tool_call_id == 'toolu_1'
        assert 'created w1' in result_message.content

    async def test_arguments_given_as_json_text_are_parsed(self):
        llm = ScriptedLLM(
            [
                {'call': {'name': 'create_workflow', 'arguments': '{"title": "w1"}'}},
                text('Done'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        history = await agent.run('make a workflow')

        assert history[2].tool_calls[0].arguments == {'title': 'w1'}

    async def test_the_call_is_sent_in_the_same_run_and_the_next(self):
        llm = CallAwareLLM(
            [
                call('create_workflow', title='w1'),
                text('Done'),
                text('FINAL'),
                text('It is w1'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        await agent.run('make a workflow')
        await agent.run('what did you name it?')

        expected_call = ('create_workflow', {'title': 'w1'}, None)
        # Within the run: the request after the tool ran.
        assert [m.get('call') for m in llm.requests[1]][-2] == expected_call
        assert llm.requests[1][-1]['role'] == 'function'
        # On the next turn: rebuilt from history.
        next_turn = llm.requests[3]
        assert [m['role'] for m in next_turn] == [
            'system',
            'user',
            'assistant',
            'function',
            'assistant',
            'user',
        ]
        assert next_turn[2]['call'] == expected_call

    async def test_a_stored_conversation_can_be_passed_back_in(self):
        llm = CallAwareLLM([text('It is w1'), text('FINAL')])
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        await agent.run([*STORED_TURN, UserMessage(content='what did you name it?')])

        request = llm.requests[0]
        assert request[2]['call'] == ('create_workflow', {'title': 'w1'}, 'toolu_1')
        assert request[2]['content'] == 'On it.'
        assert request[3] == {
            'role': 'function',
            'name': 'create_workflow',
            'content': 'created w1',
            'tool_use_id': 'toolu_1',
        }

    async def test_a_call_with_no_result_is_not_sent(self):
        dangling = [
            UserMessage(content='make a workflow'),
            AssistantMessage(
                content='On it.',
                tool_calls=[
                    ToolCall(name='create_workflow', arguments={'title': 'w1'})
                ],
            ),
        ]
        llm = CallAwareLLM([text('ok'), text('FINAL')])
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        await agent.run([*dangling, UserMessage(content='are you there?')])

        request = llm.requests[0]
        assert all('call' not in message for message in request)
        assert request[2] == {'role': 'assistant', 'content': 'On it.'}

    async def test_a_failed_call_is_answered_even_when_the_run_fails(self):
        llm = ScriptedLLM(
            [
                call_with_id('create_workflow', 'toolu_1', title='w1'),
                text('not recoverable'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool(fail=True)])

        with pytest.raises(AgentError):
            await agent.run('make a workflow')

        result = agent.conversation_history[-1]
        assert isinstance(result, FunctionMessage)
        assert result.tool_call_id == 'toolu_1'
        assert result.content.startswith('Tool execution error')

    async def test_malformed_arguments_still_record_the_call(self):
        llm = ScriptedLLM(
            [
                {'call': {'name': 'create_workflow', 'arguments': '{not json'}},
                text('not recoverable'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        with pytest.raises(AgentError):
            await agent.run('make a workflow')

        call_message, result = agent.conversation_history[-2:]
        assert call_message.tool_calls[0].arguments == {}
        assert isinstance(result, FunctionMessage)


class TestProviderFormats:
    calls = [ToolCall(name='create_workflow', arguments={'title': 'w1'}, id='toolu_1')]

    def test_openai(self):
        llm = OpenAI(model='gpt-4o-mini', api_key='x')

        assert llm.format_tool_call_message('', self.calls) == {
            'role': 'assistant',
            'content': None,
            'tool_calls': [
                {
                    'id': 'toolu_1',
                    'type': 'function',
                    'function': {
                        'name': 'create_workflow',
                        'arguments': '{"title": "w1"}',
                    },
                }
            ],
        }
        assert llm.format_function_result_message(
            'create_workflow', 'created w1', 'toolu_1'
        ) == {'role': 'tool', 'tool_call_id': 'toolu_1', 'content': 'created w1'}

    async def test_openai_history_gives_an_id_to_a_call_stored_without_one(self):
        agent = Agent('a', 'sys', OpenAI(model='gpt-5.4', api_key='x'))
        agent.add_to_history(
            [
                UserMessage(content='make a workflow'),
                AssistantMessage(
                    content='',
                    tool_calls=[
                        ToolCall(name='create_workflow', arguments={'title': 'w1'})
                    ],
                ),
                FunctionMessage(content='created w1', name='create_workflow'),
                AssistantMessage(content='Done.'),
            ]
        )

        messages = await agent._get_message_history()

        call_id = messages[1]['tool_calls'][0]['id']
        assert call_id
        assert messages[2] == {
            'role': 'tool',
            'tool_call_id': call_id,
            'content': 'created w1',
        }
        # No message uses the role newer models reject.
        assert all(message['role'] != 'function' for message in messages)

    async def test_openai_requests_tools_one_call_at_a_time(self):
        from unittest.mock import AsyncMock

        llm = OpenAI(model='gpt-5.4', api_key='x')
        reply = MagicMock(content='ok', tool_calls=None, function_call=None)
        llm.client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=reply)], usage=None)
        )

        await llm.generate(
            [{'role': 'user', 'content': 'hi'}],
            functions=[{'name': 'lookup', 'parameters': {'type': 'object'}}],
        )

        sent = llm.client.chat.completions.create.call_args.kwargs
        assert sent['tools'] == [
            {
                'type': 'function',
                'function': {'name': 'lookup', 'parameters': {'type': 'object'}},
            }
        ]
        assert sent['parallel_tool_calls'] is False
        assert 'functions' not in sent

    async def test_openai_drops_a_temperature_the_model_refuses(self):
        from unittest.mock import AsyncMock

        import httpx
        from openai import BadRequestError

        llm = OpenAI(model='gpt-5.5', api_key='x', temperature=0)
        refusal = BadRequestError(
            "Unsupported value: 'temperature' does not support 0 with this model.",
            response=httpx.Response(
                400, request=httpx.Request('POST', 'https://api.openai.com/v1')
            ),
            body={'param': 'temperature', 'code': 'unsupported_value'},
        )
        reply = MagicMock(content='ok', tool_calls=None, function_call=None)
        ok = MagicMock(choices=[MagicMock(message=reply)], usage=None)
        create = AsyncMock(side_effect=[refusal, ok, ok])
        llm.client.chat.completions.create = create

        await llm.generate([{'role': 'user', 'content': 'hi'}])
        await llm.generate([{'role': 'user', 'content': 'again'}])

        sent = [call.kwargs for call in create.call_args_list]
        assert 'temperature' in sent[0]
        assert 'temperature' not in sent[1]
        # Remembered: the next request does not try it again.
        assert 'temperature' not in sent[2]
        assert len(sent) == 3

    async def test_openai_other_bad_requests_are_not_retried(self):
        from unittest.mock import AsyncMock

        import httpx
        from openai import BadRequestError

        llm = OpenAI(model='gpt-5.5', api_key='x')
        error = BadRequestError(
            'bad messages',
            response=httpx.Response(
                400, request=httpx.Request('POST', 'https://api.openai.com/v1')
            ),
            body={'param': 'messages'},
        )
        create = AsyncMock(side_effect=error)
        llm.client.chat.completions.create = create

        with pytest.raises(BadRequestError):
            await llm.generate([{'role': 'user', 'content': 'hi'}])

        assert create.await_count == 1

    async def test_openai_reads_the_tool_call_and_its_id(self):
        llm = OpenAI(model='gpt-5.4', api_key='x')
        call = MagicMock(id='call_abc')
        call.function.name = 'lookup'
        call.function.arguments = '{"q": 1}'
        response = MagicMock(tool_calls=[call], function_call=None)

        assert await llm.get_function_call(response) == {
            'name': 'lookup',
            'arguments': '{"q": 1}',
            'id': 'call_abc',
        }

    def test_anthropic(self):
        llm = Anthropic(model='claude-sonnet-5-5', api_key='x')

        assert llm.format_tool_call_message('On it.', self.calls) == {
            'role': 'assistant',
            'content': [
                {'type': 'text', 'text': 'On it.'},
                {
                    'type': 'tool_use',
                    'id': 'toolu_1',
                    'name': 'create_workflow',
                    'input': {'title': 'w1'},
                },
            ],
        }

    async def test_anthropic_history_pairs_the_call_with_its_result(self):
        agent = Agent('a', 'sys', Anthropic(model='claude-sonnet-5-5', api_key='x'))
        agent.add_to_history(STORED_TURN)

        messages = await agent._get_message_history()

        assert messages[1]['content'][1]['id'] == 'toolu_1'
        assert messages[2]['tool_use_id'] == 'toolu_1'

    def test_a_provider_without_a_format_leaves_the_call_out(self):
        assert ScriptedLLM([]).format_tool_call_message('', self.calls) is None

    def test_guarded_llm_uses_the_wrapped_providers_tool_handling(self):
        inner = Anthropic(model='claude-sonnet-5-5', api_key='x')
        guarded = GuardedLLM(inner, MagicMock())

        assert guarded.format_tool_call_message('', self.calls) == (
            inner.format_tool_call_message('', self.calls)
        )
        response = {'content': '', 'raw_content': ['blocks']}
        assert guarded.get_assistant_message_for_tool_call(response) == ['blocks']


class TestAgentEvents:
    async def test_one_event_per_message_the_run_adds(self):
        events = []
        llm = ScriptedLLM(
            [
                call('create_workflow', title='w1'),
                text('Done'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        history = await agent.run('make a workflow', on_event=events.append)

        assert [(e.type, e.is_final) for e in events] == [
            (AgentEventType.TOOL_CALL, False),
            (AgentEventType.TOOL_RESULT, False),
            (AgentEventType.MESSAGE, True),
        ]
        assert all(event.agent == 'a' for event in events)
        # The events are the turn: everything after the system message and
        # the caller's input.
        assert [event.message for event in events] == history[2:]

    async def test_an_async_callback_is_awaited(self):
        seen = []

        async def on_event(event):
            seen.append(event.type)

        agent = Agent('a', 'sys', ScriptedLLM([text('hello')]))
        await agent.run('hi', on_event=on_event)

        assert seen == [AgentEventType.MESSAGE]

    async def test_a_failing_callback_does_not_stop_the_run(self):
        def on_event(event):
            raise RuntimeError('database is down')

        llm = ScriptedLLM(
            [call('create_workflow', title='w1'), text('Done'), text('FINAL')]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool()])

        history = await agent.run('make a workflow', on_event=on_event)

        assert history[-1].content == 'Done'
        # Nothing but the scripted calls: the failure was not sent for analysis.
        assert len(llm.requests) == 3

    async def test_requests_to_continue_are_reported_as_notices(self):
        events = []
        llm = ScriptedLLM(
            [
                plan(('create it', 'in_progress')),
                text('I think that is all'),
                plan(('create it', 'completed')),
                text('Created.'),
            ]
        )
        agent = Agent('a', 'sys', llm, reasoning_pattern=ReasoningPattern.PLAN_EXECUTE)

        await agent.run('make a workflow', on_event=events.append)

        assert [(e.type, e.is_final) for e in events] == [
            (AgentEventType.TOOL_CALL, False),
            (AgentEventType.TOOL_RESULT, False),
            (AgentEventType.MESSAGE, False),
            (AgentEventType.NOTICE, False),
            (AgentEventType.TOOL_CALL, False),
            (AgentEventType.TOOL_RESULT, False),
            (AgentEventType.MESSAGE, True),
        ]
        assert isinstance(events[3].message, UserMessage)

    async def test_a_tool_error_is_reported_as_a_result(self):
        events = []
        llm = ScriptedLLM(
            [call('create_workflow', title='w1'), text('not recoverable')]
        )
        agent = Agent('a', 'sys', llm, tools=[create_tool(fail=True)])

        with pytest.raises(AgentError):
            await agent.run('make a workflow', on_event=events.append)

        assert [e.type for e in events] == [
            AgentEventType.TOOL_CALL,
            AgentEventType.TOOL_RESULT,
        ]

    async def test_the_callback_does_not_outlive_the_run(self):
        events = []
        agent = Agent('a', 'sys', ScriptedLLM([text('one'), text('two')]))

        await agent.run('hi', on_event=events.append)
        await agent.run('again')

        assert len(events) == 1

    async def test_system_messages_are_not_reported(self):
        events = []
        agent = Agent('a', 'sys', ScriptedLLM([text('hello')]))

        await agent.run('hi', on_event=events.append)

        assert not any(isinstance(e.message, SystemMessage) for e in events)
