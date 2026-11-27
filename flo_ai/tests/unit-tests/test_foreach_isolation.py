"""ForEach items do not see each other through agent conversation history.

Agents inside a ForEach are the same instances on every item, and an agent's
history is never cleared by the workflow. Without isolation, item k was sent to
the model together with items 1..k-1 and the replies to them.
"""

import base64
from types import SimpleNamespace

import pytest

from flo_ai import DocumentMessageContent
from flo_ai.agent import Agent
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.nodes import AriumNode, ForEachNode, FunctionNode, _reachable_agents
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models import UserMessage


class RecordingLLM(BaseLLM):
    """Replies with the user turns it was sent, so a reply shows what leaked in."""

    def __init__(self, calls):
        super().__init__(model='fake-model', api_key='key')
        # A shared list: agent builders copy the LLM, and the copy keeps this.
        self.calls = calls

    async def generate(self, messages, functions=None, output_schema=None):
        user_turns = [m['content'] for m in messages if m['role'] == 'user']
        self.calls.append(user_turns)
        return {'content': 'saw:' + ','.join(user_turns)}

    async def stream(self, messages, functions=None, output_schema=None, **kwargs):
        yield {'content': ''}

    def get_message_content(self, response):
        return response['content']

    def format_tool_for_llm(self, tool):
        return {'tool': tool}

    def format_tools_for_llm(self, tools):
        return [{'tool': t} for t in tools]

    def format_image_in_message(self, image):
        return {'image': image}


def _text(message):
    content = getattr(message, 'content', message)
    return getattr(content, 'text', content)


def _agent(calls, name='extractor'):
    return Agent(name=name, system_prompt='Extract.', llm=RecordingLLM(calls))


def _items(*texts):
    return [UserMessage(text) for text in texts]


async def test_each_item_is_sent_alone():
    calls = []
    agent = _agent(calls)

    results = await ForEachNode(name='batch', execute_node=agent).run(
        _items('a', 'b', 'c')
    )

    assert calls == [['a'], ['b'], ['c']]
    assert [_text(r) for r in results] == ['saw:a', 'saw:b', 'saw:c']
    assert agent.conversation_history == []


async def test_history_from_before_the_loop_is_kept():
    calls = []
    agent = _agent(calls)
    earlier = UserMessage('earlier')
    agent.conversation_history = [earlier]

    await ForEachNode(name='batch', execute_node=agent).run(_items('a', 'b'))

    assert calls == [['earlier', 'a'], ['earlier', 'b']]
    assert agent.conversation_history == [earlier]


async def test_history_is_restored_when_an_item_fails():
    calls = []
    agent = _agent(calls)

    def boom(inputs, variables=None, **kwargs):
        raise RuntimeError('downstream failure')

    boom_node = FunctionNode(name='boom', function=boom)
    inner = (
        AriumBuilder()
        .add_agent(agent)
        .add_function_node(boom_node)
        .start_with(agent)
        .connect(agent, boom_node)
        .end_with(boom_node)
        .build()
    )
    foreach = ForEachNode(name='batch', execute_node=AriumNode('one', inner))

    with pytest.raises(RuntimeError, match='downstream failure'):
        await foreach.run(_items('a'))

    assert calls == [['a']]
    assert agent.conversation_history == []


async def test_agent_two_workflow_levels_down_end_to_end():
    """ForEach -> per-item sub-workflow -> referenced workflow -> agent.

    The shape wavefront produces when it inlines a referenced single-agent
    workflow into a per-document sub-workflow.
    """
    yaml_config = """
    arium:
      ariums:
        - name: one_doc
          ariums:
            - name: classify
              agents:
                - name: classifier
                  job: "Classify the document."
              workflow:
                start: classifier
                edges: []
                end: [classifier]
          workflow:
            start: classify
            edges: []
            end: [classify]
      iterators:
        - name: batch
          execute_node: one_doc
          input_filter: [input]
          forward_all_results: true
      function_nodes:
        - name: collect
          function_name: collect
          input_filter: [batch]
      workflow:
        start: batch
        edges:
          - from: batch
            to: [collect]
        end: [collect]
    """

    def collect(inputs, variables=None, **kwargs):
        return [_text(i) for i in inputs]

    calls = []
    arium = AriumBuilder.from_yaml(
        yaml_str=yaml_config,
        base_llm=RecordingLLM(calls),
        function_registry={'collect': collect},
    ).build()

    result = await arium.run(_items('a', 'b', 'c'))

    assert calls == [['a'], ['b'], ['c']]
    assert result[-1].result.content == ['saw:a', 'saw:b', 'saw:c']


class CacheWatchingLLM(RecordingLLM):
    """Records how many formatted copies each document holds at call time."""

    def __init__(self, documents):
        super().__init__([])
        self.documents = documents
        self.cache_sizes = []

    async def generate(self, messages, functions=None, output_schema=None):
        self.cache_sizes.append([len(d._formatted_cache) for d in self.documents])
        return {'content': 'done'}


async def test_each_items_formatted_copy_is_released_after_it():
    documents = [
        DocumentMessageContent(
            base64=base64.b64encode(text.encode()).decode(), mime_type='text/plain'
        )
        for text in ('first', 'second')
    ]
    llm = CacheWatchingLLM(documents)
    agent = Agent(name='reader', system_prompt='Read.', llm=llm)

    await ForEachNode(name='batch', execute_node=agent).run(
        [UserMessage(content=d) for d in documents]
    )

    # Formatted while its own item runs; never more than one held at a time.
    assert llm.cache_sizes == [[1, 0], [0, 1]]
    assert [d._formatted_cache for d in documents] == [{}, {}]


class TestReachableAgents:
    def test_bare_agent(self):
        agent = _agent([])

        assert _reachable_agents(agent) == [agent]

    def test_through_nested_workflows_and_foreach(self):
        inner_agent = _agent([], name='inner')
        sibling = _agent([], name='sibling')
        inner = AriumNode('inner', SimpleNamespace(nodes={'inner': inner_agent}))
        middle = AriumNode(
            'middle',
            SimpleNamespace(
                nodes={
                    'inner': inner,
                    'sibling': ForEachNode(name='each', execute_node=sibling),
                }
            ),
        )

        assert _reachable_agents(middle) == [inner_agent, sibling]

    def test_agent_reachable_twice_is_listed_once(self):
        agent = _agent([])
        shared = SimpleNamespace(nodes={'agent': agent})
        outer = AriumNode(
            'outer',
            SimpleNamespace(
                nodes={'x': AriumNode('x', shared), 'y': AriumNode('y', shared)}
            ),
        )

        assert _reachable_agents(outer) == [agent]

    def test_function_node_has_none(self):
        node = FunctionNode(name='fn', function=lambda **kwargs: None)

        assert _reachable_agents(node) == []
