"""A workflow's memory is reset after every run, not only a successful one.

Kept after a failure, it held that run's inputs - attached files included -
until the next run, which then started on top of the failed run's items.
"""

import asyncio

import pytest

from flo_ai import UserMessage
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.events import AriumEventType
from flo_ai.arium.memory import MessageMemory
from flo_ai.arium.nodes import FunctionNode


def _text(message):
    return getattr(message, 'content', message)


def _single_node(function):
    node = FunctionNode(name='step', function=function)
    return (
        AriumBuilder().add_function_node(node).start_with(node).end_with(node).build()
    )


async def test_memory_is_empty_after_a_failed_run():
    def fail(**kwargs):
        raise RuntimeError('step failed')

    arium = _single_node(fail)

    with pytest.raises(RuntimeError):
        await arium.run([UserMessage('first')])

    assert arium.memory.get() == []


async def test_next_run_does_not_see_the_failed_runs_items():
    seen = []

    def record_then_fail_once(inputs, **kwargs):
        seen.append([_text(i) for i in inputs])
        if len(seen) == 1:
            raise RuntimeError('step failed')
        return 'ok'

    arium = _single_node(record_then_fail_once)

    with pytest.raises(RuntimeError):
        await arium.run([UserMessage('first')])
    await arium.run([UserMessage('second')])

    assert seen == [['first'], ['second']]


async def test_memory_is_empty_after_a_cancelled_run():
    started = asyncio.Event()

    async def wait_forever(**kwargs):
        started.set()
        await asyncio.Event().wait()

    arium = _single_node(wait_forever)
    task = asyncio.create_task(arium.run([UserMessage('first')]))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert arium.memory.get() == []


class CustomMemory(MessageMemory):
    pass


class MemoryWithArguments(MessageMemory):
    def __init__(self, label):
        super().__init__()
        self.label = label


def _with_memory(memory, function):
    node = FunctionNode(name='step', function=function)
    return (
        AriumBuilder()
        .with_memory(memory)
        .add_function_node(node)
        .start_with(node)
        .end_with(node)
        .build()
    )


@pytest.mark.parametrize('fails', [False, True])
async def test_reset_keeps_the_configured_memory_type(fails):
    def step(**kwargs):
        if fails:
            raise RuntimeError('step failed')
        return 'ok'

    arium = _with_memory(CustomMemory(), step)

    try:
        await arium.run([UserMessage('first')])
    except RuntimeError:
        pass

    assert type(arium.memory) is CustomMemory
    assert arium.memory.get() == []


async def test_memory_needing_arguments_is_replaced_by_a_plain_one():
    arium = _with_memory(MemoryWithArguments('x'), lambda **kwargs: 'ok')

    await arium.run([UserMessage('first')])

    assert type(arium.memory) is MessageMemory


async def test_failure_callback_still_sees_the_runs_memory():
    def fail(**kwargs):
        raise RuntimeError('step failed')

    arium = _single_node(fail)
    sizes = []

    def on_event(event):
        if event.event_type == AriumEventType.WORKFLOW_FAILED:
            sizes.append(len(arium.memory.get()))

    with pytest.raises(RuntimeError):
        await arium.run([UserMessage('first')], event_callback=on_event)

    assert sizes == [1]
