"""Provenance tagging and variable propagation for Arium nodes.

Covers two behaviours a downstream consumer depends on:

1. Every message carries the name of the node that produced it, on the message
   itself, so the tag survives being unwrapped out of ``MessageMemoryItem``.
2. ``FunctionNode`` receives the workflow's variables, like every other node
   type that can act on them.
"""

import pytest

from flo_ai.arium.arium import Arium
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.arium.nodes import FunctionNode
from flo_ai.models import UserMessage


class TestMessageProvenanceTag:
    def test_tags_message_with_producing_node(self):
        message = UserMessage(content='{"a": 1}')

        MessageMemoryItem(node='node_a', result=message)

        assert message.metadata['node'] == 'node_a'

    def test_preserves_existing_metadata(self):
        message = UserMessage(content='hi', metadata={'source': 'upload'})

        MessageMemoryItem(node='node_a', result=message)

        assert message.metadata == {'source': 'upload', 'node': 'node_a'}

    def test_retag_on_bubble_up_wins(self):
        """A nested result re-stored by a parent takes the parent's node name.

        The tag must describe the memory doing the filtering, so that
        `input_filter` values and tags always agree. The parent reads it off its
        own item, which is the only view that has to be right.
        """
        message = UserMessage(content='{}')

        inner = MessageMemoryItem(node='inner_node', result=message)
        outer = MessageMemoryItem(node='outer_node', result=message)

        assert outer.result.metadata['node'] == 'outer_node'
        # The inner memory still describes what it actually produced.
        assert inner.result.metadata['node'] == 'inner_node'

    def test_reassigning_a_producer_does_not_mutate_the_shared_message(self):
        """`run` hands its results back to the caller, who may pass them into
        another workflow. Retagging in place there would rewrite the tags inside
        the results the caller is still holding, so the new tag goes on a copy.
        """
        message = UserMessage(content='{}', metadata={'source': 'upload'})
        MessageMemoryItem(node='node_a', result=message)

        item = MessageMemoryItem(node='node_b', result=message)

        assert item.result is not message
        assert message.metadata['node'] == 'node_a'
        assert item.result.metadata == {'source': 'upload', 'node': 'node_b'}
        # The copy is shallow: the payload is shared, only the tag differs.
        assert item.result.content is message.content

    def test_tolerates_result_without_metadata(self):
        """`.result` is occasionally a plain str, which has no metadata."""
        item = MessageMemoryItem(node='node_a', result='not a message')

        assert item.result == 'not a message'

    def test_tag_survives_memory_roundtrip(self):
        """The tag has to outlive `[item.result for item in memory.get()]`."""
        memory = MessageMemory()
        memory.add(
            MessageMemoryItem(node='node_a', result=UserMessage(content='{"x":1}'))
        )
        memory.add(
            MessageMemoryItem(node='node_b', result=UserMessage(content='{"y":2}'))
        )

        inputs = [item.result for item in memory.get(['node_a', 'node_b'])]

        assert [m.metadata['node'] for m in inputs] == ['node_a', 'node_b']

    def test_repeated_node_keeps_its_own_tag_per_message(self):
        """A ForEach forwards N results all tagged with the same node name."""
        messages = [UserMessage(content='{}') for _ in range(3)]
        for message in messages:
            MessageMemoryItem(node='iterator', result=message)

        assert all(m.metadata['node'] == 'iterator' for m in messages)

    def test_receiving_a_message_does_not_overwrite_its_producer(self):
        """retag=False marks a message that is received rather than produced."""
        message = UserMessage(content='{}')

        MessageMemoryItem(node='node_a', result=message)
        MessageMemoryItem(node='input', result=message, retag=False)

        assert message.metadata['node'] == 'node_a'

    def test_an_untagged_message_is_tagged_even_when_receiving(self):
        """A real workflow input has no prior producer, so it becomes 'input'."""
        message = UserMessage(content='{}')

        MessageMemoryItem(node='input', result=message, retag=False)

        assert message.metadata['node'] == 'input'

    async def test_passing_a_result_into_a_subworkflow_preserves_its_tag(self):
        """The failure this guards against.

        A node's output is passed straight into a nested workflow, which seeds it
        into its own memory as 'input'. Because both memories hold the SAME
        BaseMessage, retagging there used to erase the producer — so a downstream
        node reading provenance saw 'input' instead of the node that made it.
        """
        parent = Arium(memory=MessageMemory())
        produced = UserMessage(content='{"label": "classified"}')
        parent.memory.add(MessageMemoryItem(node='classifier', result=produced))

        # What an AriumNode does: hand the parent's memory to a nested workflow.
        nested = Arium(memory=MessageMemory())
        inputs = [item.result for item in parent.memory.get()]
        for message in inputs:
            nested.memory.add(
                MessageMemoryItem(node='input', result=message, retag=False)
            )

        assert produced.metadata['node'] == 'classifier'
        # And the parent's own view is unchanged.
        assert [i.result.metadata['node'] for i in parent.memory.get()] == [
            'classifier'
        ]

    def test_a_top_level_input_is_retagged(self):
        """Preserving provenance is only correct for a parent handing inputs
        down. A caller can pass a message that already carries a tag — feeding
        one workflow's results into another, or reusing a message object — and
        that tag names a node in some other workflow. It must not survive into
        this one, where it would drive filtering and routing.
        """
        message = UserMessage(content='{}', metadata={'node': 'other_workflow_node'})

        item = MessageMemoryItem(node='input', result=message, retag=True)

        assert item.result.metadata['node'] == 'input'
        # ...and the caller's copy is left as they gave it.
        assert message.metadata['node'] == 'other_workflow_node'


class TestFunctionNodeReceivesVariables:
    async def test_variables_reach_the_function(self):
        seen = {}

        async def capture(inputs=None, variables=None, **kwargs):
            seen['variables'] = variables
            return 'done'

        node = FunctionNode(name='capture', function=capture)
        arium = Arium(memory=MessageMemory())

        await arium._dispatch_node_run(
            node, 'function', [UserMessage(content='{}')], {'tone': 'formal'}
        )

        assert seen['variables'] == {'tone': 'formal'}

    async def test_empty_variables_are_passed_through(self):
        seen = {}

        async def capture(inputs=None, variables=None, **kwargs):
            seen['variables'] = variables
            return 'done'

        node = FunctionNode(name='capture', function=capture)
        arium = Arium(memory=MessageMemory())

        await arium._dispatch_node_run(node, 'function', [], {})

        assert seen['variables'] == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
