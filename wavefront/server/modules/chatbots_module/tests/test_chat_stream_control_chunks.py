"""A guardrail control chunk reaches the client as a dict.

A guarded stream can release text and then retract it, and it says so with a
control chunk rather than content. This consumer handles that by yielding the
control chunk to the controller which sends the `retract: True` frame.
"""

from types import SimpleNamespace

from flo_ai.guardrails import control_chunk

from chatbots_module.services.chat_inference_service import ChatInferenceService


class _FakeLlm:
    def __init__(self, chunks):
        self._chunks = chunks

    async def stream(self, messages):
        for chunk in self._chunks:
            yield chunk


def _session():
    return SimpleNamespace(id='session-1', system_prompt_snapshot='prompt')


async def _collect(chunks):
    service = ChatInferenceService(llm_inference_config_service=None)
    return [delta async for delta in service.stream(_FakeLlm(chunks), _session(), [])]


class TestControlChunks:
    async def test_content_chunks_pass_through(self):
        assert await _collect([{'content': 'he'}, {'content': 'llo'}]) == ['he', 'llo']

    async def test_a_retract_control_chunk_is_yielded(self):
        chunks = [
            {'content': 'my card is 4111'},
            control_chunk('retract', 'Part withheld.', replacement='my card is ****'),
        ]

        expected_control = {
            'action': 'retract',
            'message': 'Part withheld.',
            'replacement': 'my card is ****',
        }
        assert await _collect(chunks) == ['my card is 4111', expected_control]

    async def test_an_unknown_control_action_is_also_yielded(self):
        chunks = [control_chunk('something-new', 'n/a'), {'content': 'hi'}]

        expected_control = {
            'action': 'something-new',
            'message': 'n/a',
            'replacement': None,
        }
        assert await _collect(chunks) == [expected_control, 'hi']

    async def test_empty_and_contentless_chunks_are_still_skipped(self):
        assert await _collect([{}, {'content': ''}, None, {'content': 'x'}]) == ['x']
