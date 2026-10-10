"""Tests for ReasoningPattern.PLAN_EXECUTE and agents used as tools."""

import pytest

from flo_ai.agent import Agent, AgentBuilder, ReasoningPattern
from flo_ai.agent.agent import MAX_CONTINUATION_NUDGES
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.guarded_llm import GuardrailBlocked
from flo_ai.tool import Plan, PlanStepStatus, Tool, agent_as_tool, create_plan_tool
from flo_ai.tool.plan_tool import PLAN_TOOL_NAME


class ScriptedLLM(BaseLLM):
    """Replays a fixed list of responses and records every request."""

    def __init__(self, responses):
        self.model = 'scripted'
        self.temperature = 0
        self.kwargs = {}
        self.api_key = None
        self.responses = list(responses)
        self.requests = []

    async def generate(self, messages, functions=None, output_schema=None, **kwargs):
        # Copied: the agent keeps appending to the list it passed in.
        self.requests.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def stream(self, *args, **kwargs):
        yield None

    def get_message_content(self, response):
        return response.get('text')

    async def get_function_call(self, response):
        return response.get('call')

    def format_tool_for_llm(self, tool):
        return {'name': tool.name}

    def format_tools_for_llm(self, tools):
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image):
        return ''

    async def format_document_in_message(self, document):
        return ''


def text(content):
    return {'text': content}


def call(name, **arguments):
    return {'call': {'name': name, 'arguments': arguments}}


def plan(*steps):
    return call(
        PLAN_TOOL_NAME,
        steps=[{'description': d, 'status': s} for d, s in steps],
    )


def lookup_tool(calls):
    async def lookup(query: str) -> str:
        calls.append(query)
        return f'result for {query}'

    return Tool(
        name='lookup',
        description='Look something up',
        function=lookup,
        parameters={'query': {'type': 'string', 'description': 'What to look up'}},
    )


def final_text(history):
    return history[-1].content


class TestPlan:
    def test_empty_plan_is_not_complete(self):
        assert Plan().is_complete() is False

    def test_update_replaces_steps(self):
        p = Plan()
        p.update([{'description': 'a', 'status': 'completed'}, 'b'])

        assert [s.status for s in p.steps] == [
            PlanStepStatus.COMPLETED,
            PlanStepStatus.PENDING,
        ]
        assert [s.description for s in p.unfinished()] == ['b']

    def test_completed_and_skipped_steps_finish_the_plan(self):
        p = Plan()
        p.update(
            [
                {'description': 'a', 'status': 'completed'},
                {'description': 'b', 'status': 'skipped'},
            ]
        )
        assert p.is_complete() is True

    def test_update_accepts_a_json_string(self):
        p = Plan()
        p.update('[{"description": "a", "status": "pending"}]')
        assert len(p.steps) == 1

    @pytest.mark.parametrize(
        'steps',
        [
            [],
            'not json',
            [{'status': 'pending'}],
            [{'description': 'a', 'status': 'done'}],
            [42],
        ],
    )
    def test_invalid_update_is_rejected_and_keeps_the_plan(self, steps):
        p = Plan()
        p.update(['existing'])

        with pytest.raises(ValueError):
            p.update(steps)

        assert [s.description for s in p.steps] == ['existing']

    async def test_tool_reports_an_invalid_plan_as_a_result(self):
        p = Plan()
        result = await create_plan_tool(p).execute(steps=[])

        assert result.startswith('Plan not updated')
        assert p.steps == []


class TestPlanExecuteAgent:
    def test_pattern_adds_the_plan_tool(self):
        agent = Agent(
            'a', 'sys', ScriptedLLM([]), reasoning_pattern=ReasoningPattern.PLAN_EXECUTE
        )
        assert PLAN_TOOL_NAME in agent.tools_dict

    def test_other_patterns_have_no_plan(self):
        agent = Agent('a', 'sys', ScriptedLLM([]))
        assert agent.plan is None
        assert agent.tools == []

    async def test_plans_executes_and_answers(self):
        lookups = []
        llm = ScriptedLLM(
            [
                plan(('find x', 'in_progress'), ('find y', 'pending')),
                call('lookup', query='x'),
                plan(('find x', 'completed'), ('find y', 'in_progress')),
                call('lookup', query='y'),
                plan(('find x', 'completed'), ('find y', 'completed')),
                text('x and y found'),
            ]
        )
        agent = Agent(
            'a',
            'sys',
            llm,
            tools=[lookup_tool(lookups)],
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await agent.run('find x and y')

        assert final_text(history) == 'x and y found'
        assert lookups == ['x', 'y']
        assert agent.plan.is_complete()
        # Six scripted replies and nothing else: a finished plan settles
        # whether the answer is final without a classifier call.
        assert len(llm.requests) == 6
        assert PLAN_TOOL_NAME in llm.requests[0][0]['content']

    async def test_direct_answer_needs_no_plan(self):
        llm = ScriptedLLM([text('4')])
        agent = Agent('a', 'sys', llm, reasoning_pattern=ReasoningPattern.PLAN_EXECUTE)

        history = await agent.run('2 + 2?')

        assert final_text(history) == '4'
        assert len(llm.requests) == 1

    async def test_early_answer_is_sent_back_with_the_unfinished_plan(self):
        llm = ScriptedLLM(
            [
                plan(('find x', 'in_progress'), ('find y', 'pending')),
                text('I think I am done'),
                plan(('find x', 'completed'), ('find y', 'skipped')),
                text('x found'),
            ]
        )
        agent = Agent('a', 'sys', llm, reasoning_pattern=ReasoningPattern.PLAN_EXECUTE)

        history = await agent.run('find x and y')

        assert final_text(history) == 'x found'
        # The request after the early answer carries that answer and the nudge.
        roles_and_content = [(m['role'], m['content']) for m in llm.requests[2][-2:]]
        assert roles_and_content[0] == ('assistant', 'I think I am done')
        assert roles_and_content[1][0] == 'user'
        assert 'find y' in roles_and_content[1][1]

    async def test_plan_updates_do_not_use_up_max_tool_calls(self):
        lookups = []
        llm = ScriptedLLM(
            [
                plan(('a', 'in_progress')),
                plan(('a', 'in_progress'), ('b', 'pending')),
                plan(('a', 'in_progress'), ('b', 'pending'), ('c', 'pending')),
                call('lookup', query='a'),
                text('answer after the limit'),
            ]
        )
        agent = Agent(
            'a',
            'sys',
            llm,
            tools=[lookup_tool(lookups)],
            max_tool_calls=1,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await agent.run('go')

        assert lookups == ['a']
        assert final_text(history) == 'answer after the limit'

    async def test_plan_updates_are_bounded(self):
        # max_tool_calls=1 allows 2 * 1 + 2 = 4 plan updates.
        llm = ScriptedLLM([plan(('a', 'pending'))] * 4 + [text('forced answer')])
        agent = Agent(
            'a',
            'sys',
            llm,
            max_tool_calls=1,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await agent.run('go')

        assert final_text(history) == 'forced answer'
        assert len(llm.requests) == 5

    async def test_plan_is_reset_between_runs(self):
        llm = ScriptedLLM([plan(('a', 'completed')), text('one'), text('two')])
        agent = Agent('a', 'sys', llm, reasoning_pattern=ReasoningPattern.PLAN_EXECUTE)

        await agent.run('first')
        assert agent.plan.is_complete()

        await agent.run('second')
        assert agent.plan.steps == []

    def test_yaml_settings(self):
        builder = AgentBuilder.from_yaml(
            yaml_str="""
agent:
  name: supervisor
  job: Coordinate the work.
  settings:
    reasoning_pattern: PLAN_EXECUTE
    max_tool_calls: 20
""",
            base_llm=ScriptedLLM([]),
        )
        agent = builder.build()

        assert agent.reasoning_pattern == ReasoningPattern.PLAN_EXECUTE
        assert agent.max_tool_calls == 20
        assert agent.plan is not None


class TestContinuationNudge:
    async def test_intermediate_replies_cannot_loop_forever(self):
        """A model that keeps reasoning without calling a tool is stopped."""
        responses = []
        for _ in range(MAX_CONTINUATION_NUDGES + 1):
            responses += [text('Let me check the schema first'), text('INTERMEDIATE')]
        llm = ScriptedLLM(responses)
        agent = Agent('a', 'sys', llm, tools=[lookup_tool([])])

        history = await agent.run('hi')

        assert final_text(history) == 'Let me check the schema first'
        main_requests = llm.requests[::2]
        assert len(main_requests) == MAX_CONTINUATION_NUDGES + 1
        # Each nudge reaches the model: the request grows by the reply and the
        # nudge every time, instead of being resent unchanged.
        assert [len(r) for r in main_requests] == [
            2 + 2 * i for i in range(MAX_CONTINUATION_NUDGES + 1)
        ]


class TestAgentAsTool:
    async def test_returns_the_agents_final_answer(self):
        worker = Agent('researcher', 'sys', ScriptedLLM([text('found it')]))
        tool = agent_as_tool(worker, 'Finds things')

        assert tool.name == 'researcher'
        assert tool.description == 'Finds things'
        assert await tool.execute(task='find it') == 'found it'

    def test_defaults(self):
        worker = Agent('data analyst', 'sys', ScriptedLLM([]), role='an analyst')
        tool = worker.as_tool()

        assert tool.name == 'data_analyst'
        assert tool.description == 'an analyst'

    async def test_each_delegation_starts_from_an_empty_conversation(self):
        llm = ScriptedLLM([text('one'), text('two')])
        tool = agent_as_tool(Agent('worker', 'sys', llm))

        await tool.execute(task='first task')
        await tool.execute(task='second task')

        second_request = [m['content'] for m in llm.requests[1]]
        assert 'second task' in second_request
        assert 'first task' not in second_request
        assert 'one' not in second_request

    async def test_worker_failure_is_returned_to_the_caller(self):
        worker = Agent('worker', 'sys', ScriptedLLM([RuntimeError('boom')] * 2))
        result = await agent_as_tool(worker).execute(task='do it')

        assert result.startswith('worker failed')

    async def test_guardrail_block_propagates(self):
        worker = Agent('worker', 'sys', ScriptedLLM([GuardrailBlocked('blocked')]))
        supervisor = Agent(
            'supervisor',
            'sys',
            ScriptedLLM([call('worker', task='do it')]),
            tools=[worker.as_tool()],
        )

        with pytest.raises(GuardrailBlocked):
            await supervisor.run('go')

    async def test_supervisor_delegates_and_answers(self):
        researcher_llm = ScriptedLLM([text('revenue was 10')])
        analyst_llm = ScriptedLLM([text('that is up 25%')])
        researcher = Agent('researcher', 'sys', researcher_llm)
        analyst = Agent('analyst', 'sys', analyst_llm)

        supervisor_llm = ScriptedLLM(
            [
                plan(('get revenue', 'in_progress'), ('analyse it', 'pending')),
                call('researcher', task='get revenue'),
                plan(('get revenue', 'completed'), ('analyse it', 'in_progress')),
                call('analyst', task='analyse revenue of 10'),
                plan(('get revenue', 'completed'), ('analyse it', 'completed')),
                text('Revenue was 10, up 25%.'),
            ]
        )
        supervisor = Agent(
            'supervisor',
            'Coordinate the work.',
            supervisor_llm,
            tools=[
                researcher.as_tool('Finds figures'),
                analyst.as_tool('Analyses figures'),
            ],
            max_tool_calls=10,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
        )

        history = await supervisor.run('How did revenue do?')

        assert final_text(history) == 'Revenue was 10, up 25%.'
        # Each worker saw only its task, not the supervisor's conversation.
        assert [m['content'] for m in researcher_llm.requests[0]] == [
            'sys',
            'get revenue',
        ]
        assert [m['content'] for m in analyst_llm.requests[0]] == [
            'sys',
            'analyse revenue of 10',
        ]
        # The workers' answers came back to the supervisor as tool results.
        last_request = str(supervisor_llm.requests[-1])
        assert 'revenue was 10' in last_request
        assert 'that is up 25%' in last_request
