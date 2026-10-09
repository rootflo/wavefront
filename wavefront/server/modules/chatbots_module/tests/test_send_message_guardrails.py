"""A policy block reaches the caller as a policy block, on both paths.

`send_message` wraps generation in a bare `except Exception` that answers 502
with MODEL_FAILURE_MESSAGE -- "Your message was saved; please retry". For a
refusal both halves are wrong: nothing was saved, and `GuardrailBlocked` is
not retryable. Worse, swallowing it there means the app-level handler that
knows how to format a decision never runs.

The other half is ordering. The user's message used to be committed before any
inbound check ran, so a refused turn was stored anyway and every retry stored
it again. The check now runs first, which is also the last moment the streaming
path can still pick a status code -- after `StreamingResponse` is returned,
only an in-band frame is left.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flo_ai.llm.guarded_llm import GuardrailBlocked

from chatbots_module.controllers.chat_session_controller import (
    MODEL_FAILURE_MESSAGE,
    send_message,
)
from chatbots_module.models.chat_schemas import SendMessagePayload
from common_module.response_formatter import ResponseFormatter

SESSION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _blocked(message='This request was refused by policy.'):
    # block_reasons is read by GuardrailBlocked's constructor, not by us.
    decision = SimpleNamespace(
        blocked=True,
        caller_message=lambda subject: message,
        operator_summary=lambda: 'adapter=stub',
        block_reasons=lambda: ['stub said no'],
    )
    return GuardrailBlocked(message, decision)


class _FakeInference:
    """Hand-rolled rather than AsyncMock: `stream` has to be a real async gen."""

    def __init__(self, check_error=None, stream_error=None, deltas=()):
        self.check_error = check_error
        self.stream_error = stream_error
        self.deltas = deltas

    async def resolve_llm(self, chatbot, user_id=None):
        return object()

    async def check_user_message(self, chatbot, content, user_id=None):
        if self.check_error:
            raise self.check_error

    async def stream(self, llm, session, history):
        for delta in self.deltas:
            yield delta
        if self.stream_error:
            raise self.stream_error

    async def generate(self, llm, session, history):
        raise AssertionError('not used by these tests')


def _services(inference):
    chatbot_service = AsyncMock()
    chatbot_service.get_chatbot.return_value = SimpleNamespace(
        enabled=True, namespace='acme', name='support-bot'
    )

    chat_session_service = AsyncMock()
    chat_session_service.get_owned_session.return_value = SimpleNamespace(
        id=SESSION_ID, chatbot_id=uuid.uuid4(), system_prompt_snapshot='prompt'
    )
    chat_session_service.add_message.return_value = SimpleNamespace(
        id=uuid.uuid4(), to_dict=lambda: {}
    )
    chat_session_service.get_history.return_value = []

    return {
        'request': SimpleNamespace(
            state=SimpleNamespace(session=SimpleNamespace(user_id=str(USER_ID)))
        ),
        'response_formatter': ResponseFormatter(),
        'chatbot_service': chatbot_service,
        'chat_session_service': chat_session_service,
        'chat_inference_service': inference,
    }


async def _call(services, stream, content='hello'):
    return await send_message(
        session_id=SESSION_ID,
        payload=SendMessagePayload(content=content),
        stream=stream,
        **services,
    )


async def _frames(response):
    return [chunk async for chunk in response.body_iterator]


class TestInputBlock:
    async def test_it_propagates_so_the_app_handler_can_format_it(self):
        services = _services(_FakeInference(check_error=_blocked()))

        with pytest.raises(GuardrailBlocked):
            await _call(services, stream=False)

    async def test_nothing_is_written_for_a_refused_turn(self):
        # The point of checking before the insert: a refused message must not
        # sit in the thread, and a retry must not add a second copy.
        services = _services(_FakeInference(check_error=_blocked()))

        with pytest.raises(GuardrailBlocked):
            await _call(services, stream=False)

        services['chat_session_service'].add_message.assert_not_awaited()

    async def test_the_streaming_path_also_fails_before_the_headers_go_out(self):
        # Raising here rather than inside the generator is what lets this be a
        # status code instead of a 200 with an error buried in the stream.
        services = _services(_FakeInference(check_error=_blocked()))

        with pytest.raises(GuardrailBlocked):
            await _call(services, stream=True)

        services['chat_session_service'].add_message.assert_not_awaited()


class TestOutputBlockWhileStreaming:
    async def test_the_frame_carries_the_policy_message_not_the_provider_one(self):
        services = _services(_FakeInference(stream_error=_blocked('Refused.')))

        frames = await _frames(await _call(services, stream=True))

        assert len(frames) == 1
        assert json.loads(frames[0].removeprefix('data: ')) == {'error': 'Refused.'}
        assert MODEL_FAILURE_MESSAGE not in frames[0]

    async def test_no_assistant_message_is_persisted(self):
        # One write, for the user's turn. Buffering means no delta reached the
        # transcript, so there is no partial reply to keep either.
        services = _services(_FakeInference(stream_error=_blocked()))

        await _frames(await _call(services, stream=True))

        assert services['chat_session_service'].add_message.await_count == 1

    async def test_an_ordinary_provider_failure_still_reports_generically(self):
        # The generic message is still right for a provider fault: the turn was
        # saved and retrying may work. Only a block is special-cased.
        services = _services(_FakeInference(stream_error=RuntimeError('boom')))

        frames = await _frames(await _call(services, stream=True))

        assert json.loads(frames[-1].removeprefix('data: ')) == {
            'error': MODEL_FAILURE_MESSAGE
        }


class TestCleanTurn:
    async def test_deltas_then_done(self):
        services = _services(_FakeInference(deltas=['he', 'llo']))

        frames = await _frames(await _call(services, stream=True))

        assert [json.loads(f.removeprefix('data: ')) for f in frames[:2]] == [
            {'content': 'he'},
            {'content': 'llo'},
        ]
        assert json.loads(frames[-1].removeprefix('data: '))['done'] is True
