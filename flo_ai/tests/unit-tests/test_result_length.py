"""`*.result.length` span attributes measure the final message's text.

They used to be `len(str(result))` over a whole history or workflow memory,
which built a string containing every attached file just to take its length.
"""

from contextlib import contextmanager

import pytest

from flo_ai import (
    AssistantMessage,
    DocumentMessageContent,
    TextMessageContent,
    UserMessage,
)
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemoryItem
from flo_ai.arium.nodes import FunctionNode
from flo_ai.telemetry.instrumentation import result_length


class Sentinel:
    """Fails the test if anything turns it into text."""

    def __repr__(self):
        raise AssertionError('the whole result was stringified')

    __str__ = __repr__


@pytest.mark.parametrize(
    'result, expected',
    [
        ('abc', 3),
        (UserMessage('abcd'), 4),
        (AssistantMessage(content='abcde'), 5),
        (UserMessage(content=TextMessageContent(text='ab')), 2),
        (MessageMemoryItem(node='n', result=UserMessage('abc')), 3),
        (UserMessage(content=DocumentMessageContent(base64='QUJD' * 1000)), 0),
        ({'rows': 1}, len(str({'rows': 1}))),
        ([], 0),
        (None, len('None')),
    ],
)
def test_measures_the_final_text(result, expected):
    assert result_length(result) == expected


def test_a_list_is_measured_by_its_last_entry_only():
    assert result_length([Sentinel(), UserMessage('xyz')]) == 3


class FakeSpan:
    def __init__(self, attributes):
        self.attributes = attributes

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        pass


class FakeTracer:
    def __init__(self):
        self.attributes = {}

    @contextmanager
    def start_as_current_span(self, name, attributes=None):
        yield FakeSpan(self.attributes)


async def test_workflow_span_records_the_final_text_length(monkeypatch):
    tracer = FakeTracer()
    monkeypatch.setattr('flo_ai.arium.arium.get_tracer', lambda: tracer)
    node = FunctionNode(name='answer', function=lambda **kwargs: 'final answer')
    arium = AriumBuilder().add_function_node(node).start_with(node).end_with(node)

    await arium.build().run(
        [UserMessage(content=DocumentMessageContent(base64='QUJD' * 100_000))]
    )

    assert tracer.attributes['workflow.result.length'] == len('final answer')
