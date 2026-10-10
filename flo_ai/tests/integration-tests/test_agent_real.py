#!/usr/bin/env python3
"""
Real-API tests for the agent loop: tool calls kept in history, replaying a
stored conversation, per-step events, plan-and-execute, and agents used as tools.

The provider files next to this one test each LLM class on its own. These run
an Agent end to end, because the failures they guard against only show up when
a provider is sent a request the agent built: an unanswered tool call, a result
with no call before it, a system message in the wrong place.

Each test runs once per provider and is skipped when that provider's key is
not set: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY.

    uv run pytest -m integration tests/integration-tests/test_agent_real.py
"""

import json
import os

import pytest

from flo_ai.agent import Agent, AgentEventType, ReasoningPattern
from flo_ai.arium import AriumBuilder
from flo_ai.guardrails import GuardrailsEngine, Principal, ResolvedPolicy
from flo_ai.llm import Anthropic, Gemini, OpenAI
from flo_ai.llm.guarded_llm import GuardedLLM
from flo_ai.models import AssistantMessage, FunctionMessage, ToolCall, UserMessage
from flo_ai.models.agent_error import AgentError
from flo_ai.tool import Tool, parallel_agents_tool

# Codes a model cannot guess, so finding one in an answer shows that the
# tool's result reached it.
ORDERS = {
    'A-1001': 'Shipped. Tracking code ZX-4471.',
    'B-2002': 'Held at customs. Reference code QP-9080.',
}

PROVIDERS = ['openai', 'anthropic', 'gemini']

# Providers whose message format carries the tool call itself, not only the
# result (see BaseLLM.format_tool_call_message).
PROVIDERS_SENT_THE_CALL = ['openai', 'anthropic']


def make_llm(provider: str):
    """Build the provider's LLM, or skip the test when its key is not set."""
    if provider == 'openai':
        if not os.getenv('OPENAI_API_KEY'):
            pytest.skip('OPENAI_API_KEY environment variable not set')
        return OpenAI(
            model='gpt-4o-mini', api_key=os.getenv('OPENAI_API_KEY'), temperature=0
        )
    if provider == 'anthropic':
        if not os.getenv('ANTHROPIC_API_KEY'):
            pytest.skip('ANTHROPIC_API_KEY environment variable not set')
        return Anthropic(
            model='claude-opus-5-5',
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            temperature=0,
        )
    if provider == 'gemini':
        if not os.getenv('GOOGLE_API_KEY'):
            pytest.skip('GOOGLE_API_KEY environment variable not set')
        return Gemini(
            model='gemini-2.5-flash',
            api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0,
        )
    raise ValueError(f'Unknown provider: {provider}')


def order_tool(lookups: list, fail: bool = False) -> Tool:
    """A lookup tool that records the order ids it was asked for."""

    async def get_order_status(order_id: str) -> str:
        lookups.append(order_id)
        if fail:
            raise RuntimeError('The order database is offline.')
        return ORDERS.get(order_id, f'No order with id {order_id}.')

    return Tool(
        name='get_order_status',
        description='Look up the current status of an order by its id',
        function=get_order_status,
        parameters={
            'order_id': {'type': 'string', 'description': 'The order id, e.g. A-1001'}
        },
    )


def order_agent(llm, lookups: list, **kwargs) -> Agent:
    return Agent(
        name='support',
        system_prompt=(
            'You answer questions about orders. Always look an order up with '
            'the get_order_status tool before answering, and include any '
            'code from the result in your answer.'
        ),
        llm=llm,
        tools=[order_tool(lookups)],
        **kwargs,
    )


def answer(history) -> str:
    content = history[-1].content
    return str(getattr(content, 'text', content))


def tool_call_messages(history):
    return [m for m in history if isinstance(m, AssistantMessage) and m.tool_calls]


@pytest.fixture(params=PROVIDERS)
def provider(request):
    return request.param


@pytest.fixture
def llm(provider):
    return make_llm(provider)


@pytest.mark.integration
class TestToolCallsReal:
    """A tool call, its result, and the turns that come after."""

    @pytest.mark.asyncio
    async def test_tool_result_reaches_the_answer(self, llm):
        """The request sent after the tool ran is one the provider accepts."""
        lookups = []
        agent = order_agent(llm, lookups)

        history = await agent.run('What is the status of order A-1001?')

        assert lookups == ['A-1001']
        assert 'ZX-4471' in answer(history)

    @pytest.mark.asyncio
    async def test_call_and_result_are_recorded_as_a_pair(self, llm):
        lookups = []
        agent = order_agent(llm, lookups)

        history = await agent.run('What is the status of order A-1001?')

        calls = tool_call_messages(history)
        assert len(calls) == 1
        call = calls[0].tool_calls[0]
        assert call.name == 'get_order_status'
        assert call.arguments == {'order_id': 'A-1001'}

        result = history[history.index(calls[0]) + 1]
        assert isinstance(result, FunctionMessage)
        assert result.name == 'get_order_status'
        assert result.tool_call_id == call.id
        assert 'ZX-4471' in result.content

    @pytest.mark.asyncio
    async def test_a_second_turn_is_accepted_after_a_tool_call(self, llm):
        """The next request is rebuilt from history, tool call included."""
        lookups = []
        agent = order_agent(llm, lookups)

        await agent.run('What is the status of order A-1001?')
        history = await agent.run(
            'Which tracking code did you just give me? Answer from our '
            'conversation, without looking anything up again.'
        )

        assert 'ZX-4471' in answer(history)

    @pytest.mark.parametrize('provider', PROVIDERS_SENT_THE_CALL, indirect=True)
    @pytest.mark.asyncio
    async def test_a_later_turn_knows_the_arguments_of_an_earlier_call(self, llm):
        """The arguments are only in the call, so this needs the call replayed.

        The user never states the order id as such, and the tool's result
        does not repeat it.
        """
        lookups = []
        agent = order_agent(llm, lookups)

        await agent.run(
            'Check the order whose id is the letter A, a dash, then one '
            'thousand and one written in digits.'
        )
        history = await agent.run(
            'Exactly which order id did you pass to the tool? Reply with the id only.'
        )

        assert lookups[0] == 'A-1001'
        assert 'A-1001' in answer(history)

    @pytest.mark.asyncio
    async def test_two_lookups_in_one_turn(self, llm):
        lookups = []
        agent = order_agent(llm, lookups)

        history = await agent.run(
            'Give me the status of order A-1001 and of order B-2002.'
        )

        assert sorted(lookups) == ['A-1001', 'B-2002']
        assert 'ZX-4471' in answer(history)
        assert 'QP-9080' in answer(history)

    @pytest.mark.asyncio
    async def test_final_answer_after_the_tool_call_limit(self, llm):
        """Hitting max_tool_calls rebuilds the request from history."""
        lookups = []
        agent = order_agent(llm, lookups, max_tool_calls=1)

        history = await agent.run(
            'Give me the status of order A-1001 and of order B-2002.'
        )

        assert len(lookups) == 1
        assert isinstance(history[-1], AssistantMessage)
        assert not history[-1].tool_calls
        assert answer(history)

    @pytest.mark.asyncio
    async def test_a_failing_tool_is_answered_in_history(self, llm):
        """With no retries the run fails, and the call is not left unanswered."""
        lookups = []
        agent = Agent(
            name='support',
            system_prompt='Look orders up with the get_order_status tool.',
            llm=llm,
            tools=[order_tool(lookups, fail=True)],
            max_retries=0,
        )

        with pytest.raises(AgentError):
            await agent.run('What is the status of order A-1001?')

        call_message, result = agent.conversation_history[-2:]
        assert call_message.tool_calls[0].name == 'get_order_status'
        assert isinstance(result, FunctionMessage)
        assert result.content.startswith('Tool execution error')

    @pytest.mark.asyncio
    async def test_the_agent_recovers_after_a_failed_run(self, llm):
        """A turn after a failed tool call is still a valid request."""
        lookups = []
        agent = Agent(
            name='support',
            system_prompt='Look orders up with the get_order_status tool.',
            llm=llm,
            tools=[order_tool(lookups, fail=True)],
            max_retries=0,
        )
        with pytest.raises(AgentError):
            await agent.run('What is the status of order A-1001?')

        # Same conversation, tool now working.
        agent.tools = [order_tool(lookups)]
        agent.tools_dict = {tool.name: tool for tool in agent.tools}
        history = await agent.run('Please try order A-1001 once more.')

        assert 'ZX-4471' in answer(history)


@pytest.mark.integration
class TestStoredConversationReal:
    """Saving a turn from its events and continuing it on a fresh agent."""

    @pytest.mark.asyncio
    async def test_events_replayed_on_a_new_agent(self, llm):
        question = UserMessage(content='What is the status of order A-1001?')
        stored = [question]

        first = order_agent(llm, [])
        await first.run([question], on_event=lambda event: stored.append(event.message))

        lookups = []
        second = order_agent(llm, lookups)
        history = await second.run(
            [
                *stored,
                UserMessage(
                    content='Which tracking code did you just give me? Answer '
                    'from our conversation, without looking anything up again.'
                ),
            ]
        )

        assert 'ZX-4471' in answer(history)

    @pytest.mark.asyncio
    async def test_events_are_the_messages_the_run_added(self, llm):
        events = []
        agent = order_agent(llm, [])

        history = await agent.run(
            'What is the status of order A-1001?', on_event=events.append
        )

        types = [event.type for event in events]
        assert types[:2] == [AgentEventType.TOOL_CALL, AgentEventType.TOOL_RESULT]
        assert types[-1] == AgentEventType.MESSAGE
        assert events[-1].is_final
        assert [event.is_final for event in events[:-1]] == [False] * (len(events) - 1)
        # System message and the question come first; everything after is the run's.
        assert [event.message for event in events] == history[2:]

    @pytest.mark.asyncio
    async def test_a_stored_call_with_no_result_does_not_break_the_next_turn(self, llm):
        """A session saved mid-call (a dropped connection) must stay usable."""
        stored = [
            UserMessage(content='What is the status of order A-1001?'),
            AssistantMessage(
                content='Let me look that up.',
                tool_calls=[
                    ToolCall(
                        name='get_order_status',
                        arguments={'order_id': 'A-1001'},
                        id='toolu_interrupted_1',
                    )
                ],
            ),
        ]
        lookups = []
        agent = order_agent(llm, lookups)

        history = await agent.run(
            [*stored, UserMessage(content='Are you still there? Please check A-1001.')]
        )

        assert 'ZX-4471' in answer(history)

    @pytest.mark.parametrize('provider', PROVIDERS_SENT_THE_CALL, indirect=True)
    @pytest.mark.asyncio
    async def test_formatted_call_and_result_are_accepted(self, llm):
        """format_tool_call_message output, sent straight to the provider."""
        tool = order_tool([])
        functions = llm.format_tools_for_llm([tool])
        messages = [
            {
                'role': 'user',
                'content': 'Use get_order_status to check order A-1001.',
            }
        ]

        response = await llm.generate(messages, functions=functions)
        function_call = await llm.get_function_call(response)
        assert function_call is not None, 'the model did not call the tool'

        arguments = function_call['arguments']
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        call = ToolCall(
            name=function_call['name'],
            arguments=arguments,
            id=llm.get_tool_use_id(function_call),
        )

        call_message = llm.format_tool_call_message(
            llm.get_message_content(response) or '', [call]
        )
        assert call_message is not None
        messages.append(call_message)
        messages.append(
            llm.format_function_result_message(call.name, ORDERS['A-1001'], call.id)
        )

        final = await llm.generate(messages, functions=functions)

        assert 'ZX-4471' in llm.get_message_content(final)


@pytest.mark.integration
class TestGuardedToolCallsReal:
    """A guarded LLM must use the wrapped provider's tool-call handling."""

    @pytest.mark.asyncio
    async def test_tool_call_through_a_guarded_llm(self, llm):
        class NoPolicy:
            async def resolve(self, principal):
                return ResolvedPolicy()

        engine = GuardrailsEngine(resolver=NoPolicy(), adapters=[])
        guarded = GuardedLLM(llm, engine, Principal(namespace='integration'))
        lookups = []
        agent = order_agent(guarded, lookups)

        history = await agent.run('What is the status of order A-1001?')
        history = await agent.run(
            'Which tracking code did you just give me? Answer from our '
            'conversation, without looking anything up again.'
        )

        assert lookups == ['A-1001']
        assert 'ZX-4471' in answer(history)


@pytest.mark.integration
class TestPlanExecuteReal:
    @pytest.mark.asyncio
    async def test_agent_plans_then_finishes_the_plan(self, llm):
        lookups = []
        agent = order_agent(
            llm,
            lookups,
            max_tool_calls=10,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await agent.run(
            'Check order A-1001, then check order B-2002, then tell me which '
            'of the two is held at customs. Plan the steps first.'
        )

        assert agent.plan.steps, 'the agent did not make a plan'
        assert agent.plan.is_complete()
        assert sorted(lookups) == ['A-1001', 'B-2002']
        assert 'B-2002' in answer(history)

    @pytest.mark.asyncio
    async def test_a_direct_question_needs_no_plan(self, llm):
        agent = Agent(
            name='helper',
            system_prompt='You are a concise assistant.',
            llm=llm,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await agent.run('What is 2 + 2? Reply with the number only.')

        assert '4' in answer(history)

    @pytest.mark.asyncio
    async def test_plan_updates_are_reported_as_tool_calls(self, llm):
        events = []
        agent = order_agent(
            llm,
            [],
            max_tool_calls=10,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        await agent.run(
            'Check order A-1001, then check order B-2002, then summarise '
            'both. Plan the steps first.',
            on_event=events.append,
        )

        called = [
            event.message.tool_calls[0].name
            for event in events
            if event.type == AgentEventType.TOOL_CALL
        ]
        assert 'update_plan' in called
        assert 'get_order_status' in called


@pytest.mark.integration
class TestAgentsAsToolsReal:
    def workers(self, llm, lookups):
        researcher = Agent(
            name='order_desk',
            system_prompt=(
                'You look orders up with the get_order_status tool and report '
                'the result word for word, including any code.'
            ),
            llm=llm,
            tools=[order_tool(lookups)],
        )
        writer = Agent(
            name='writer',
            system_prompt='You rewrite the text you are given as one polite sentence.',
            llm=llm,
        )
        return researcher, writer

    @pytest.mark.asyncio
    async def test_supervisor_delegates_to_a_worker(self, llm):
        lookups = []
        order_desk, _ = self.workers(llm, lookups)
        supervisor = Agent(
            name='supervisor',
            system_prompt=(
                'You coordinate specialists and cannot look anything up '
                'yourself. Delegate to them and report what they find, '
                'including any code.'
            ),
            llm=llm,
            tools=[order_desk.as_tool('Looks up the status of an order by its id')],
            max_tool_calls=6,
        )

        history = await supervisor.run('What is the status of order A-1001?')

        assert lookups == ['A-1001']
        assert 'ZX-4471' in answer(history)

    @pytest.mark.asyncio
    async def test_parallel_tool_runs_real_workers(self, llm):
        """The tool is called directly, so only the workers depend on the model."""
        lookups = []
        order_desk, writer = self.workers(llm, lookups)
        tool = parallel_agents_tool([order_desk, writer])

        result = await tool.execute(
            tasks=[
                {'agent': 'order_desk', 'task': 'Look up order B-2002.'},
                {
                    'agent': 'writer',
                    'task': 'Rewrite this: your parcel left the warehouse.',
                },
            ]
        )

        assert lookups == ['B-2002']
        assert 'QP-9080' in result
        assert '[1] order_desk' in result
        assert '[2] writer' in result

    @pytest.mark.asyncio
    async def test_supervisor_from_workflow_yaml(self, llm):
        yaml_str = """
arium:
  agents:
    - name: supervisor
      job: >
        You coordinate specialists and cannot look anything up yourself.
        Delegate to them and report what they find, including any code.
        The customer is called <customer>.
      settings:
        max_tool_calls: 6
      tools:
        - name: order_desk
          description_override: Looks up the status of an order by its id
    - name: order_desk
      job: >
        You look orders up with the get_order_status tool and report the
        result word for word, including any code.
      tools:
        - get_order_status
  workflow:
    start: supervisor
    edges: []
    end: [supervisor]
"""
        lookups = []
        arium = AriumBuilder.from_yaml(
            yaml_str=yaml_str,
            base_llm=llm,
            tool_registry={'get_order_status': order_tool(lookups)},
        ).build()

        result = await arium.run(
            'What is the status of order A-1001?', variables={'customer': 'Priya'}
        )

        assert 'order_desk' not in arium.nodes
        assert lookups == ['A-1001']
        assert 'ZX-4471' in str(result[-1].result.content)


@pytest.mark.integration
class TestAgentBehaviourReal:
    @pytest.mark.asyncio
    async def test_system_prompt_is_followed_with_history_before_it(self, llm):
        """The system message leads the request, whatever was added first."""
        agent = Agent(
            name='helper',
            system_prompt='Whatever you are asked, reply with the single word PINEAPPLE.',
            llm=llm,
        )

        history = await agent.run(
            [
                UserMessage(content='Hello there.'),
                AssistantMessage(content='PINEAPPLE'),
                UserMessage(content='What is the capital of France?'),
            ]
        )

        assert 'PINEAPPLE' in answer(history).upper()

    @pytest.mark.asyncio
    async def test_new_variables_take_effect_on_a_reused_agent(self, llm):
        agent = Agent(
            name='helper',
            system_prompt='Whatever you are asked, reply with the single word <word>.',
            llm=llm,
        )

        first = await agent.run('Go.', variables={'word': 'ALPHA'})
        agent.clear_history()
        second = await agent.run('Go.', variables={'word': 'BRAVO'})

        assert 'ALPHA' in answer(first).upper()
        assert 'BRAVO' in answer(second).upper()

    @pytest.mark.asyncio
    async def test_react_answer_has_no_final_answer_marker(self, llm):
        lookups = []
        agent = order_agent(llm, lookups, reasoning_pattern=ReasoningPattern.REACT)

        history = await agent.run('What is the status of order A-1001?')

        assert 'ZX-4471' in answer(history)
        assert 'final answer:' not in answer(history).lower()

    @pytest.mark.asyncio
    async def test_a_revisited_workflow_agent_gets_a_valid_request(self, llm):
        """writer -> critic -> writer: the second visit rebuilds from memory."""
        from typing import Literal

        writer = Agent(
            name='writer',
            system_prompt=(
                'Write one sentence about the sea. If there is feedback in the '
                'conversation, rewrite your sentence to follow it.'
            ),
            llm=llm,
        )
        critic = Agent(
            name='critic',
            system_prompt=(
                'You are an editor reviewing a sentence about the sea. Give '
                'one short piece of feedback: ask the writer to mention a '
                'lighthouse. Write the word LIGHTHOUSE in capitals.'
            ),
            llm=llm,
        )
        route = iter(['critic', 'writer_done'])

        def after_writer(memory) -> Literal['critic', 'writer_done']:
            return next(route)

        done = Agent(
            name='writer_done',
            system_prompt='Repeat the most recent sentence about the sea, word for word.',
            llm=llm,
        )
        arium = (
            AriumBuilder()
            .add_agents([writer, critic, done])
            .start_with(writer)
            .add_edge(writer, [critic, done], after_writer)
            .add_edge(critic, [writer])
            .end_with(done)
            .build()
        )

        result = await arium.run('Please write about the sea.')

        # What the writer was sent on its second visit: the task once, its
        # first draft, and the critic's feedback. Checked from its history and
        # not from the final text, which depends on how the model took the
        # feedback.
        second_visit = [str(m.content) for m in writer.conversation_history]
        assert second_visit.count('Please write about the sea.') == 1
        assert any('LIGHTHOUSE' in text.upper() for text in second_visit)
        assert len(second_visit) == 5  # system, task, draft, feedback, new draft
        assert str(result[-1].result.content).strip()


@pytest.mark.integration
class TestInteractiveAgentReal:
    """An agent in a chat session with a person."""

    @pytest.mark.asyncio
    async def test_angle_brackets_survive_across_turns(self, llm):
        agent = Agent(
            name='helper',
            system_prompt='You are a concise assistant.',
            llm=llm,
            interactive=True,
        )

        await agent.run(
            'My template contains the placeholder <workflow_name>. Repeat that '
            'placeholder back to me, angle brackets included.'
        )
        history = await agent.run(
            'Thanks. Which placeholder was it? Write it with its angle brackets.'
        )

        assert '<workflow_name>' in answer(history)

    @pytest.mark.asyncio
    async def test_a_question_is_asked_and_the_next_turn_answers_it(self, llm):
        lookups = []
        agent = Agent(
            name='support',
            system_prompt=(
                'You answer questions about orders using the get_order_status '
                'tool. If you do not know the order id, ask the customer for '
                'it; never guess one. Include any code from the result in '
                'your answer.'
            ),
            llm=llm,
            tools=[order_tool(lookups)],
            interactive=True,
        )

        first = await agent.run('Hi, can you tell me where my order is?')

        assert lookups == []
        assert '?' in answer(first)

        second = await agent.run('Sorry, it is order A-1001.')

        assert lookups == ['A-1001']
        assert 'ZX-4471' in answer(second)
