"""A revisited agent is not handed again what its history already holds.

Passing the whole workflow memory again appended every input, attached files
included, once more on each visit, and its own earlier reply as if someone else
said it. What it no longer holds - a cleared history, a memory whose view is not
append-only - must still reach it.
"""

from typing import Literal

from flo_ai import UserMessage
from flo_ai.agent import Agent
from flo_ai.arium.arium import Arium
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemory
from flo_ai.arium.nodes import AriumNode, FunctionNode
from flo_ai.llm.base_llm import BaseLLM


class RecordingLLM(BaseLLM):
    def __init__(self):
        super().__init__(model='fake-model', api_key='key')
        self.calls = []

    async def generate(self, messages, functions=None, output_schema=None):
        self.calls.append([(m['role'], m['content']) for m in messages])
        return {'content': f'draft {len(self.calls)}'}

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


def _review_loop(llm, memory=None, on_review=None):
    """writer -> reviewer -> writer -> done: the writer is visited twice."""
    writer = Agent(name='writer', system_prompt='Write.', llm=llm)

    def review(**kwargs):
        if on_review:
            on_review(writer)
        return 'tighten it'

    reviewer = FunctionNode(name='reviewer', function=review)
    done = FunctionNode(name='done', function=lambda **kwargs: 'ok')

    def after_writer(memory, execution_context) -> Literal['reviewer', 'done']:
        visits = execution_context['node_visit_count'].get('writer', 0)
        return 'done' if visits >= 2 else 'reviewer'

    builder = AriumBuilder().with_memory(memory) if memory else AriumBuilder()
    return (
        builder.add_agent(writer)
        .add_function_node(reviewer)
        .add_function_node(done)
        .start_with(writer)
        .add_edge(writer, [reviewer, done], after_writer)
        .connect(reviewer, writer)
        .end_with(done)
        .build()
    )


def _turns(call, role):
    return [content for r, content in call if r == role]


async def test_second_visit_adds_only_the_new_input():
    llm = RecordingLLM()

    await _review_loop(llm).run([UserMessage('the brief')])

    first, second = llm.calls
    assert _turns(first, 'user') == ['the brief']
    assert _turns(second, 'user') == ['the brief', 'tighten it']
    assert _turns(second, 'assistant') == ['draft 1']


async def test_history_cleared_between_visits_gets_everything_again():
    """Only what the agent still holds is skipped, so nothing is ever lost."""
    llm = RecordingLLM()

    await _review_loop(llm, on_review=lambda writer: writer.clear_history()).run(
        [UserMessage('the brief')]
    )

    assert _turns(llm.calls[1], 'user') == ['the brief', 'tighten it']


class LatestOnlyMemory(MessageMemory):
    """A memory whose view is not append-only: it shows only the newest item."""

    def get(self, include_nodes=None):
        return super().get(include_nodes)[-1:]


async def test_memory_that_is_not_append_only_loses_nothing():
    llm = RecordingLLM()

    await _review_loop(llm, memory=LatestOnlyMemory()).run([UserMessage('the brief')])

    assert _turns(llm.calls[1], 'user') == ['the brief', 'tighten it']


async def test_first_visit_is_handed_everything():
    """Nothing is filtered on a first visit, whatever the agent is called -
    even `input`, the name the workflow's own inputs are stored under."""
    llm = RecordingLLM()
    agent = Agent(name='input', system_prompt='Write.', llm=llm)
    arium = AriumBuilder().add_agent(agent).start_with(agent).end_with(agent).build()

    await arium.run([UserMessage('the brief')])

    assert _turns(llm.calls[0], 'user') == ['the brief']


async def test_revisit_with_nothing_new_does_not_end_on_the_agents_reply():
    """A retry loop whose filter shows only what the agent already holds."""
    llm = RecordingLLM()
    writer = Agent(name='writer', system_prompt='Write.', llm=llm)
    writer.input_filter = ['input']
    done = FunctionNode(name='done', function=lambda **kwargs: 'ok')

    def retry_once(memory, execution_context) -> Literal['writer', 'done']:
        visits = execution_context['node_visit_count'].get('writer', 0)
        return 'done' if visits >= 2 else 'writer'

    retry_once.supports_self_reference = True
    arium = (
        AriumBuilder()
        .add_agent(writer)
        .add_function_node(done)
        .start_with(writer)
        .add_edge(writer, [done], retry_once)
        .end_with(done)
        .build()
    )

    await arium.run([UserMessage('the brief')])

    second = [(role, content) for role, content in llm.calls[1] if role != 'system']
    assert second[-1] == ('user', 'the brief')


async def test_a_second_run_is_handed_its_new_input():
    llm = RecordingLLM()
    arium = _review_loop(llm)

    await arium.run([UserMessage('first brief')])
    await arium.run([UserMessage('second brief')])

    # The agent keeps its history across runs, as before; what matters is that
    # the second run's first visit is handed that run's input.
    assert 'second brief' in _turns(llm.calls[2], 'user')


async def test_revisited_sub_workflow_adds_only_the_new_input():
    """The sub-workflow runs afresh on each visit, but its agent is the same
    object and still holds what the first run handed it."""
    llm = RecordingLLM()
    writer = Agent(name='writer', system_prompt='Write.', llm=llm)
    drafting = (
        AriumBuilder().add_agent(writer).start_with(writer).end_with(writer).build()
    )
    reviewer = FunctionNode(name='reviewer', function=lambda **kwargs: 'tighten it')
    done = FunctionNode(name='done', function=lambda **kwargs: 'ok')

    def after_drafting(memory, execution_context) -> Literal['reviewer', 'done']:
        visits = execution_context['node_visit_count'].get('drafting', 0)
        return 'done' if visits >= 2 else 'reviewer'

    drafting_node = AriumNode('drafting', drafting)
    arium = Arium(MessageMemory())
    arium.add_nodes([drafting_node, reviewer, done])
    arium.start_at(drafting_node)
    arium.add_edge('drafting', ['reviewer', 'done'], after_drafting)
    arium.add_edge('reviewer', ['drafting'])
    arium.add_end_to(done)
    arium.compile()

    await arium.run([UserMessage('the brief')])

    first, second = llm.calls
    assert _turns(first, 'user') == ['the brief']
    assert _turns(second, 'user') == ['the brief', 'tighten it']
    assert _turns(second, 'assistant') == ['draft 1']
