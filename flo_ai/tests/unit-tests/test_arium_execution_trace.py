"""
`execution_trace` is a strict superset of `Arium.memory`: everything memory
has (final result per node, the data nodes actually receive via input_filter),
plus every intermediate message memory intentionally drops — agent tool calls
and reasoning turns, every ForEach item's internal detail, and every node of a
nested sub-workflow (AriumNode), recursively.

These tests exercise the real Agent/ForEachNode/AriumNode dispatch paths (a
scripted BaseLLM stands in for a real provider) rather than mocking them, so
a change to the collapsing behavior these guard against would actually be
caught.
"""

import pytest

from flo_ai.agent.agent import Agent
from flo_ai.arium.arium import Arium
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemory
from flo_ai.arium.nodes import AriumNode, ForEachNode, FunctionNode
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models import AssistantMessage, FunctionMessage, UserMessage
from flo_ai.tool.base_tool import Tool


class ScriptedLLM(BaseLLM):
    """Returns each response in `responses`, one per generate() call, in order."""

    def __init__(self, responses):
        super().__init__(model='scripted')
        self._responses = list(responses)
        self.call_count = 0

    async def generate(self, messages, functions=None, output_schema=None):
        response = self._responses[self.call_count]
        self.call_count += 1
        return response

    async def stream(self, messages, functions=None, output_schema=None, **kwargs):
        async def generator():
            yield {'content': ''}

        return generator()

    def get_message_content(self, response):
        return response.get('content', '')

    def format_tool_for_llm(self, tool):
        return {'name': tool.name, 'description': tool.description, 'parameters': {}}

    def format_tools_for_llm(self, tools):
        return [self.format_tool_for_llm(t) for t in tools]

    def format_image_in_message(self, image):
        return {}


async def _lookup(**kwargs):
    return 'tool-result'


def make_tool():
    return Tool(
        name='lookup', description='Looks something up', function=_lookup, parameters={}
    )


def make_tool_agent(name, responses):
    """An Agent whose one tool call is fully scripted via ScriptedLLM."""
    return Agent(
        name=name,
        system_prompt='You are a helpful agent.',
        llm=ScriptedLLM(responses),
        tools=[make_tool()],
    )


TOOL_CALL_RESPONSE = {'function_call': {'name': 'lookup', 'arguments': {}}}


def final_response(text):
    return {'content': f'Final Answer: {text}'}


class TestAgentNodeExecutionTrace:
    async def test_tool_call_and_reasoning_survive_in_trace_but_not_memory(self):
        """Only the final answer should reach `memory` (data-flow); every turn,
        including the tool call, should reach `execution_trace`."""
        agent = make_tool_agent(
            'researcher', [TOOL_CALL_RESPONSE, final_response('done')]
        )
        arium = Arium(memory=MessageMemory())

        await arium._dispatch_node_run(
            agent, 'agent', [UserMessage(content='look it up')], {}
        )

        trace_roles = [
            (item.node, type(item.result).__name__)
            for item in arium._trace_memory.get()
        ]
        assert trace_roles == [
            ('researcher', 'UserMessage'),
            ('researcher', 'SystemMessage'),
            ('researcher', 'FunctionMessage'),
            ('researcher', 'AssistantMessage'),
        ]
        function_entry = arium._trace_memory.get()[2]
        assert isinstance(function_entry.result, FunctionMessage)
        assert function_entry.result.name == 'lookup'

        # memory (the data bus) keeps only the final answer, unchanged from
        # today's behavior.
        memory_items = arium.memory.get()
        assert len(memory_items) == 0  # _dispatch_node_run alone doesn't add to memory

    async def test_revisit_does_not_duplicate_earlier_turns(self):
        """A workflow can loop back to the same agent node. The second visit's
        trace must contain only its own new turns, not a re-dump of the first
        visit's (which a naive length-based slice would produce, since
        _setup_system_message removes+re-appends the system message on every
        call and shifts list positions)."""
        agent = make_tool_agent(
            'researcher',
            [final_response('first'), TOOL_CALL_RESPONSE, final_response('second')],
        )
        arium = Arium(memory=MessageMemory())

        await arium._dispatch_node_run(agent, 'agent', [UserMessage(content='q1')], {})
        first_visit_count = len(arium._trace_memory.get())

        await arium._dispatch_node_run(agent, 'agent', [UserMessage(content='q2')], {})
        all_entries = arium._trace_memory.get()

        assert len(all_entries) > first_visit_count
        second_visit = all_entries[first_visit_count:]
        # Exactly the second visit's own turns: input, system, tool call, final.
        assert [type(e.result).__name__ for e in second_visit] == [
            'UserMessage',
            'SystemMessage',
            'FunctionMessage',
            'AssistantMessage',
        ]
        assert second_visit[0].result.content == 'q2'
        # No message object from the first visit reappears.
        first_visit_ids = {id(e.result) for e in all_entries[:first_visit_count]}
        assert not any(id(e.result) in first_visit_ids for e in second_visit)


class TestForEachNodeExecutionTrace:
    async def test_per_item_trace_is_qualified_and_complete(self):
        agent = make_tool_agent(
            'per_item_agent',
            [
                final_response('r0'),  # item 0: no tool call
                TOOL_CALL_RESPONSE,
                final_response('r1'),  # item 1: tool call then final
                final_response('r2'),  # item 2: no tool call
            ],
        )
        foreach = ForEachNode(name='classify_each', execute_node=agent)

        results = await foreach.run(
            inputs=[
                UserMessage(content='item0'),
                UserMessage(content='item1'),
                UserMessage(content='item2'),
            ],
            variables={},
        )

        assert len(results) == 3
        # Data-flow per item is untouched: one collapsed final result each.
        assert [r.content for r in results] == [
            'Final Answer: r0',
            'Final Answer: r1',
            'Final Answer: r2',
        ]

        nodes = [e.node for e in foreach.last_execution_trace]
        assert nodes.count('classify_each[0]') == 3  # input, system, final
        assert nodes.count('classify_each[1]') == 4  # input, system, tool call, final
        assert nodes.count('classify_each[2]') == 3

        item1_entries = [
            e for e in foreach.last_execution_trace if e.node == 'classify_each[1]'
        ]
        assert any(isinstance(e.result, FunctionMessage) for e in item1_entries)

    async def test_rerun_resets_trace(self):
        """last_execution_trace reflects only the most recent run(), like
        Arium.execution_trace does for a full workflow — the caller (in
        production, Arium._dispatch_node_run) must read it before calling
        run() again."""
        agent = make_tool_agent('agent', [final_response('a'), final_response('b')])
        foreach = ForEachNode(name='each', execute_node=agent)

        await foreach.run(inputs=[UserMessage(content='x')], variables={})
        # Drain round 1 the way Arium._dispatch_node_run does — immediately,
        # before run() is called again. Keeping these referenced here is also
        # what keeps them from being garbage-collected out from under a
        # subsequent identity-based diff.
        first_round = list(foreach.last_execution_trace)

        await foreach.run(inputs=[UserMessage(content='y')], variables={})
        second_round = foreach.last_execution_trace

        first_round_ids = {id(e.result) for e in first_round}
        assert not any(id(e.result) in first_round_ids for e in second_round)
        assert all(e.node == 'each[0]' for e in second_round)
        assert [type(e.result).__name__ for e in second_round] == [
            'UserMessage',
            'SystemMessage',
            'AssistantMessage',
        ]
        assert second_round[0].result.content == 'y'
        assert second_round[-1].result.content == 'Final Answer: b'


def _make_two_step_inner_arium():
    def upper(inputs=None, variables=None, **kwargs):
        text = inputs[0].content if inputs else ''
        return str(text).upper()

    def exclaim(inputs=None, variables=None, **kwargs):
        text = inputs[0].content if inputs else ''
        return f'{text}!'

    step_a = FunctionNode(name='uppercase', function=upper)
    step_b = FunctionNode(name='exclaim', function=exclaim, input_filter=['uppercase'])

    return (
        AriumBuilder()
        .add_function_node(step_a)
        .add_function_node(step_b)
        .start_with(step_a)
        .connect(step_a, step_b)
        .end_with(step_b)
        .build()
    )


class TestAriumNodeExecutionTrace:
    async def test_nested_workflow_exposes_its_own_node_breakdown(self):
        inner = _make_two_step_inner_arium()
        wrapper = AriumNode(name='text_pipeline', arium=inner)

        await wrapper.run(inputs=[UserMessage(content='hi')], variables={})

        inner_nodes = [e.node for e in inner.execution_trace]
        assert inner_nodes == ['input', 'uppercase', 'exclaim']

    async def test_parent_arium_qualifies_nested_trace_by_wrapper_name(self):
        inner = _make_two_step_inner_arium()
        wrapper = AriumNode(name='text_pipeline', arium=inner)
        outer = Arium(memory=MessageMemory())

        await outer._dispatch_node_run(
            wrapper, 'arium', [UserMessage(content='hi')], {}
        )

        qualified_nodes = [e.node for e in outer._trace_memory.get()]
        assert qualified_nodes == [
            'text_pipeline.input',
            'text_pipeline.uppercase',
            'text_pipeline.exclaim',
        ]
        # Parent's own memory (data-flow) is untouched by this — no calls to
        # _add_to_memory happened, matching today's _execute_graph_impl
        # behavior of only keeping the flattened result there.
        assert outer.memory.get() == []


class TestFullRunExposesExecutionTrace:
    async def test_execution_trace_populated_after_run(self):
        agent = make_tool_agent('answerer', [TOOL_CALL_RESPONSE, final_response('42')])
        builder = AriumBuilder().add_agent(agent).start_with(agent).end_with(agent)
        arium_instance = builder.build()

        memory_result = await arium_instance.run(
            [UserMessage(content='What is the answer?')]
        )

        # memory: one collapsed entry for the top-level node, as before.
        assert [item.node for item in memory_result] == ['input', 'answerer']
        assert isinstance(memory_result[-1].result, AssistantMessage)
        assert memory_result[-1].result.content == 'Final Answer: 42'

        # execution_trace: every turn, including the tool call.
        trace_types = [type(e.result).__name__ for e in arium_instance.execution_trace]
        assert trace_types == [
            'UserMessage',
            'UserMessage',
            'SystemMessage',
            'FunctionMessage',
            'AssistantMessage',
        ]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
