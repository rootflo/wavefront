"""Tests for parallel delegation, agents as tools in YAML, and agent-loop fixes."""

import asyncio
from typing import Literal

import pytest

from flo_ai.agent import Agent, ReasoningPattern
from flo_ai.arium import AriumBuilder
from flo_ai.arium.nodes import ForEachNode
from flo_ai.llm.guarded_llm import GuardrailBlocked
from flo_ai.models import SystemMessage, UserMessage
from flo_ai.models.agent_error import AgentError
from flo_ai.tool import Tool, parallel_agents_tool
from flo_ai.tool.agent_tool import PARALLEL_TOOL_NAME

from test_plan_execute import ScriptedLLM, call, final_text, text


class SlowLLM(ScriptedLLM):
    """Answers after a pause, recording how many calls overlapped."""

    running = 0
    most_running = 0

    async def generate(self, messages, functions=None, output_schema=None, **kwargs):
        SlowLLM.running += 1
        SlowLLM.most_running = max(SlowLLM.most_running, SlowLLM.running)
        try:
            await asyncio.sleep(0.02)
            return await super().generate(messages, functions, output_schema)
        finally:
            SlowLLM.running -= 1


@pytest.fixture(autouse=True)
def reset_slow_llm():
    SlowLLM.running = 0
    SlowLLM.most_running = 0


def contents(request):
    return [m['content'] for m in request]


def failing_tool():
    async def fail(query: str) -> str:
        raise RuntimeError('database is down')

    return Tool(
        name='lookup',
        description='Look something up',
        function=fail,
        parameters={'query': {'type': 'string', 'description': 'What to look up'}},
    )


class TestParallelDelegation:
    async def test_different_agents_run_at_the_same_time(self):
        researcher = Agent('researcher', 'sys', SlowLLM([text('facts')]))
        analyst = Agent('analyst', 'sys', SlowLLM([text('analysis')]))
        tool = parallel_agents_tool([researcher, analyst])

        result = await tool.execute(
            tasks=[
                {'agent': 'researcher', 'task': 'find facts'},
                {'agent': 'analyst', 'task': 'analyse'},
            ]
        )

        assert SlowLLM.most_running == 2
        assert '[1] researcher: find facts\nfacts' in result
        assert '[2] analyst: analyse\nanalysis' in result

    async def test_two_tasks_for_one_agent_run_in_turn(self):
        llm = SlowLLM([text('one'), text('two')])
        tool = parallel_agents_tool([Agent('worker', 'sys', llm)])

        result = await tool.execute(
            tasks=[
                {'agent': 'worker', 'task': 'first'},
                {'agent': 'worker', 'task': 'second'},
            ]
        )

        assert SlowLLM.most_running == 1
        assert '[1] worker: first\none' in result
        assert '[2] worker: second\ntwo' in result
        # The second task did not inherit the first one's conversation.
        assert contents(llm.requests[1]) == ['sys', 'second']

    @pytest.mark.parametrize(
        'tasks',
        [
            [],
            'not json',
            [{'agent': 'nobody', 'task': 'x'}],
            [{'agent': 'worker'}],
        ],
    )
    async def test_a_malformed_call_runs_nothing(self, tasks):
        llm = ScriptedLLM([])
        tool = parallel_agents_tool([Agent('worker', 'sys', llm)])

        result = await tool.execute(tasks=tasks)

        assert result.startswith('No tasks were run')
        assert llm.requests == []

    async def test_guardrail_block_propagates(self):
        blocked = Agent('blocked', 'sys', ScriptedLLM([GuardrailBlocked('no')]))
        fine = Agent('fine', 'sys', ScriptedLLM([text('ok')]))
        tool = parallel_agents_tool([blocked, fine])

        with pytest.raises(GuardrailBlocked):
            await tool.execute(
                tasks=[
                    {'agent': 'blocked', 'task': 'x'},
                    {'agent': 'fine', 'task': 'y'},
                ]
            )

    def test_tool_lists_the_agents(self):
        researcher = Agent('researcher', 'sys', ScriptedLLM([]), role='a researcher')
        analyst = Agent('analyst', 'sys', ScriptedLLM([]))
        tool = parallel_agents_tool(
            [researcher, analyst], descriptions={'analyst': 'Analyses figures'}
        )

        assert '- researcher: a researcher' in tool.description
        assert '- analyst: Analyses figures' in tool.description
        assert tool.parameters['tasks']['items']['properties']['agent']['enum'] == [
            'researcher',
            'analyst',
        ]


SUPERVISOR_YAML = """
arium:
  agents:
    - name: supervisor
      job: Coordinate the work on <topic>.
      settings:
        reasoning_pattern: PLAN_EXECUTE
        max_tool_calls: 12
      tools:
        - researcher
        - name: analyst
          description_override: Analyses figures you give it
    - name: researcher
      role: a researcher
      job: Find facts about <topic>.
    - name: analyst
      job: Analyse figures.
  workflow:
    start: supervisor
    edges: []
    end: [supervisor]
"""


class TestAgentsAsToolsInYaml:
    def build(self, yaml_str=SUPERVISOR_YAML, llm=None):
        return AriumBuilder.from_yaml(
            yaml_str=yaml_str, base_llm=llm or ScriptedLLM([])
        ).build()

    def test_listed_agents_become_tools_of_the_supervisor(self):
        arium = self.build()
        supervisor = arium.nodes['supervisor']

        assert [tool.name for tool in supervisor.tools] == [
            'researcher',
            'analyst',
            'update_plan',
            PARALLEL_TOOL_NAME,
        ]
        assert supervisor.tools_dict['researcher'].description == 'a researcher'
        assert (
            supervisor.tools_dict['analyst'].description
            == 'Analyses figures you give it'
        )
        assert '- analyst: Analyses figures you give it' in (
            supervisor.tools_dict[PARALLEL_TOOL_NAME].description
        )
        assert supervisor.max_tool_calls == 12
        assert [a.name for a in supervisor.delegate_agents()] == [
            'researcher',
            'analyst',
        ]

    def test_delegated_only_agents_are_not_workflow_nodes(self):
        arium = self.build()

        assert 'supervisor' in arium.nodes
        assert 'researcher' not in arium.nodes
        assert 'analyst' not in arium.nodes

    def test_an_agent_that_is_also_a_step_stays_a_node(self):
        yaml_str = SUPERVISOR_YAML.replace(
            'edges: []\n    end: [supervisor]',
            'edges:\n      - from: supervisor\n        to: [analyst]\n    end: [analyst]',
        )
        arium = self.build(yaml_str)

        assert 'analyst' in arium.nodes
        assert 'researcher' not in arium.nodes

    def test_a_single_worker_gets_no_parallel_tool(self):
        yaml_str = """
arium:
  agents:
    - name: supervisor
      job: Coordinate.
      tools: [researcher]
    - name: researcher
      job: Find facts.
  workflow:
    start: supervisor
    edges: []
    end: [supervisor]
"""
        supervisor = self.build(yaml_str).nodes['supervisor']
        assert [tool.name for tool in supervisor.tools] == ['researcher']

    def test_a_delegation_cycle_is_rejected(self):
        yaml_str = """
arium:
  agents:
    - name: a
      job: A.
      tools: [b]
    - name: b
      job: B.
      tools: [a]
  workflow:
    start: a
    edges: []
    end: [a]
"""
        with pytest.raises(ValueError, match='cycle: a -> b -> a'):
            self.build(yaml_str)

    async def test_workflow_variables_reach_delegated_agents(self):
        # One shared base_llm: supervisor call, researcher reply, supervisor answer.
        llm = ScriptedLLM(
            [
                call('researcher', task='look into it'),
                text('found'),
                text('all done'),
            ]
        )
        arium = self.build(llm=llm)

        result = await arium.run('go', variables={'topic': 'tides'})

        assert result[-1].result.content == 'all done'
        assert contents(llm.requests[0])[0].startswith('Coordinate the work on tides.')
        assert contents(llm.requests[1]) == [
            'You are a researcher. Find facts about tides.',
            'look into it',
        ]

    async def test_missing_variable_of_a_delegated_agent_is_reported(self):
        arium = self.build()

        with pytest.raises(ValueError, match='topic'):
            await arium.run('go')


class TestVariablesWithDelegates:
    async def test_standalone_supervisor_shares_its_variables(self):
        worker_llm = ScriptedLLM([text('done')])
        worker = Agent('worker', 'You work on <topic>.', worker_llm)
        supervisor = Agent(
            'supervisor',
            'You manage <topic>.',
            ScriptedLLM([call('worker', task='do it'), text('ok'), text('FINAL')]),
            tools=[worker.as_tool()],
        )

        await supervisor.run('go', variables={'topic': 'tides'})

        assert contents(worker_llm.requests[0]) == ['You work on tides.', 'do it']


class TestVariablesOnAReusedAgent:
    async def test_new_variables_replace_the_old_ones(self):
        llm = ScriptedLLM([text('a'), text('b')])
        agent = Agent('a', 'Speak <language>.', llm)

        await agent.run('hi', variables={'language': 'French'})
        await agent.run('hi', variables={'language': 'German'})

        assert llm.requests[0][0]['content'] == 'Speak French.'
        assert llm.requests[1][0]['content'] == 'Speak German.'

    async def test_a_run_without_variables_keeps_the_last_ones(self):
        llm = ScriptedLLM([text('a'), text('b')])
        agent = Agent('a', 'Speak <language>.', llm)

        await agent.run('hi', variables={'language': 'French'})
        await agent.run('again')

        assert llm.requests[1][0]['content'] == 'Speak French.'

    async def test_variables_add_to_the_ones_already_in_use(self):
        llm = ScriptedLLM([text('a'), text('b')])
        agent = Agent('a', 'Speak <language>.', llm)

        await agent.run('hi', variables={'language': 'French'})
        await agent.run('say <word>', variables={'word': 'tide'})

        assert contents(llm.requests[1])[0] == 'Speak French.'
        assert contents(llm.requests[1])[-1] == 'say tide'

    async def test_a_prompt_assigned_later_becomes_the_template(self):
        llm = ScriptedLLM([text('a'), text('b')])
        agent = Agent('a', 'Speak <language>.', llm)

        await agent.run('hi', variables={'language': 'French'})
        agent.system_prompt = 'Write in <language>.'
        await agent.run('hi', variables={'language': 'German'})

        assert llm.requests[1][0]['content'] == 'Write in German.'

    async def test_a_workflow_run_again_uses_the_new_variables(self):
        llm = ScriptedLLM([text('a'), text('b')])
        agent = Agent('writer', 'Speak <language>.', llm)
        arium = (
            AriumBuilder().add_agent(agent).start_with(agent).end_with(agent).build()
        )

        await arium.run('hi', variables={'language': 'French'})
        await arium.run('hi', variables={'language': 'German'})

        assert llm.requests[1][0]['content'] == 'Speak German.'


class TestHistoryInWorkflows:
    def looping_workflow(self, route):
        writer_llm = ScriptedLLM([text(f'draft {n}') for n in range(1, 6)])
        critic_llm = ScriptedLLM([text(f'notes {n}') for n in range(1, 6)])
        writer = Agent('writer', 'write', writer_llm)
        critic = Agent('critic', 'criticise', critic_llm)
        final = Agent('final', 'finish', ScriptedLLM([text('done')] * 3))
        steps = iter(route)

        def router(
            memory, execution_context=None
        ) -> Literal['writer', 'critic', 'final']:
            return next(steps)

        router.supports_self_reference = True
        arium = (
            AriumBuilder()
            .add_agents([writer, critic, final])
            .start_with(writer)
            .add_edge(writer, [critic, final], router)
            .add_edge(critic, [writer, final], router)
            .end_with(final)
            .build()
        )
        return arium, writer_llm

    async def test_a_revisited_agent_sees_each_message_once(self):
        arium, writer_llm = self.looping_workflow(['critic', 'writer', 'final'])

        await arium.run('task')

        assert contents(writer_llm.requests[1]) == [
            'write',
            'task',
            'draft 1',
            'notes 1',
        ]

    async def test_a_second_run_does_not_carry_the_first(self):
        arium, writer_llm = self.looping_workflow(['final', 'final'])

        await arium.run('first task')
        await arium.run('second task')

        assert contents(writer_llm.requests[1]) == ['write', 'second task']

    async def test_foreach_gives_each_item_a_clean_agent(self):
        llm = ScriptedLLM([text('one'), text('two')])
        node = ForEachNode('each', Agent('worker', 'sys', llm))

        await node.run([UserMessage(content='first'), UserMessage(content='second')])

        assert contents(llm.requests[1]) == ['sys', 'second']

    async def test_node_visit_cap(self, monkeypatch):
        route = ['critic', 'writer', 'critic', 'writer', 'critic', 'writer', 'final']
        arium, _ = self.looping_workflow(route)
        with pytest.raises(RuntimeError, match='visited too many times'):
            await arium.run('task')

        monkeypatch.setenv('FLO_AI_MAX_NODE_VISITS', '4')
        arium, writer_llm = self.looping_workflow(route)
        await arium.run('task')
        assert len(writer_llm.requests) == 4


class TestAgentLoopFixes:
    async def test_system_message_comes_first(self):
        llm = ScriptedLLM([text('hello')])
        agent = Agent('a', 'sys', llm)

        history = await agent.run('hi')

        assert [m['role'] for m in llm.requests[0]] == ['system', 'user']
        assert isinstance(history[0], SystemMessage)

    async def test_empty_response_is_recorded_as_the_agents_reply(self):
        agent = Agent('a', 'sys', ScriptedLLM([{}]), tools=[failing_tool()])

        history = await agent.run('hi')

        assert history[-1].role == 'assistant'
        assert not isinstance(history[-1], SystemMessage)

    async def test_tool_error_is_answered_before_the_retry(self):
        llm = ScriptedLLM(
            [
                call('lookup', query='x'),
                text('The database is down; try again.'),  # error analysis
                text('I could not look that up.'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[failing_tool()], max_retries=1)

        history = await agent.run('find x')

        assert final_text(history) == 'I could not look that up.'
        retried_request = llm.requests[2]
        assert retried_request[-1]['role'] == 'function'
        assert retried_request[-1]['name'] == 'lookup'
        assert 'database is down' in retried_request[-1]['content'].lower()

    async def test_error_analysis_is_not_sent_the_conversation(self):
        llm = ScriptedLLM([RuntimeError('boom'), text('This is unrecoverable.')])
        agent = Agent('a', 'sys', llm, max_retries=3)

        with pytest.raises(AgentError):
            await agent.run('a very particular question')

        # 'unrecoverable' stopped the retries: one failed call, one analysis.
        assert len(llm.requests) == 2
        assert 'a very particular question' not in str(llm.requests[1])

    async def test_final_answer_marker_is_stripped(self):
        llm = ScriptedLLM([text('Thought: easy.\nFinal Answer: 42')])
        agent = Agent(
            'a',
            'sys',
            llm,
            tools=[failing_tool()],
            reasoning_pattern=ReasoningPattern.REACT,
        )

        history = await agent.run('what is it?')

        assert final_text(history) == '42'

    async def test_not_final_verdict_is_read_as_intermediate(self):
        llm = ScriptedLLM(
            [
                text('Let me look that up'),
                text('NOT FINAL'),
                text('It is 42'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[failing_tool()])

        history = await agent.run('what is it?')

        assert final_text(history) == 'It is 42'
