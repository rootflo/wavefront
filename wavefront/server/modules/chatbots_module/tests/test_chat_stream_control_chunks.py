"""A guardrail control chunk never reaches the client as reply text.

A guarded stream can release text and then retract it, and it says so with a
control chunk rather than content. This consumer cannot honour that -- a delta
it has yielded is already in the client's transcript -- so it opts out by never
declaring retract support, which leaves its streams buffered and a retract
impossible.

These tests cover the case where that stops holding. `chunk.get('content')` on
a control chunk is None, so without the explicit skip it would be dropped in
silence: the withdrawn text stays on screen and nothing anywhere says so.
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

    async def test_a_retract_control_chunk_is_not_yielded_as_text(self):
        # The replacement text is the whole of what may now be shown, not a
        # delta. Appending it would leave the withdrawn text in place and add
        # the replacement after it -- the exact outcome retract exists to stop.
        chunks = [
            {'content': 'my card is 4111'},
            control_chunk('retract', 'Part withheld.', replacement='my card is ****'),
        ]

        assert await _collect(chunks) == ['my card is 4111']

    async def test_an_unknown_control_action_is_also_skipped(self):
        # Unrecognised actions are dropped rather than guessed at, matching
        # agent_stream_events._apply_control.
        chunks = [control_chunk('something-new', 'n/a'), {'content': 'hi'}]

        assert await _collect(chunks) == ['hi']

    async def test_empty_and_contentless_chunks_are_still_skipped(self):
        assert await _collect([{}, {'content': ''}, None, {'content': 'x'}]) == ['x']
