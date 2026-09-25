import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chatbots_module.services.chat_inference_service import (
    ChatInferenceError,
    ChatInferenceService,
)
from chatbots_module.utils.constants import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER


def _message(role, content):
    return SimpleNamespace(role=role, content=content)


class TestBuildMessages:
    def test_system_prompt_comes_from_the_session_snapshot(self):
        # Not from the chatbot: an edited prompt must not rewrite the premise of
        # a conversation that is already under way.
        session = SimpleNamespace(system_prompt_snapshot='pinned prompt')

        messages = ChatInferenceService.build_messages(session, [])

        assert messages == [{'role': ROLE_SYSTEM, 'content': 'pinned prompt'}]

    def test_history_follows_the_prompt_in_order(self):
        session = SimpleNamespace(system_prompt_snapshot='p')
        history = [
            _message(ROLE_ASSISTANT, 'Welcome'),
            _message(ROLE_USER, 'hello'),
            _message(ROLE_ASSISTANT, 'hi'),
        ]

        messages = ChatInferenceService.build_messages(session, history)

        assert [m['role'] for m in messages] == [
            ROLE_SYSTEM,
            ROLE_ASSISTANT,
            ROLE_USER,
            ROLE_ASSISTANT,
        ]
        assert [m['content'] for m in messages] == ['p', 'Welcome', 'hello', 'hi']


class TestResolveLlm:
    """resolve_llm is public and called by the route before it writes anything.

    If it were resolved lazily inside stream(), Starlette would already have
    sent a 200 and the headers by the time it ran, so a chatbot pointing at a
    deleted config would report success with the error buried in the stream.
    """

    def test_generate_and_stream_take_a_prebuilt_llm(self):
        # Guards the split: reintroducing a `chatbot` parameter here would mean
        # resolution moved back inside the generator.
        import inspect

        for method in (ChatInferenceService.generate, ChatInferenceService.stream):
            params = list(inspect.signature(method).parameters)
            assert params == [
                'self',
                'llm',
                'session',
                'history',
            ], f'{method.__name__} must receive an already-resolved llm'

    def test_resolve_llm_takes_the_chatbot_and_the_caller(self):
        # Guards the other half: resolve_llm is where guardrails attach, so it
        # needs the chatbot (for the namespace policy applies to) and the user
        # (for the audit trail). Losing either argument silently downgrades
        # what gets enforced or what gets attributed.
        import inspect

        params = list(inspect.signature(ChatInferenceService.resolve_llm).parameters)
        assert params == ['self', 'chatbot', 'user_id']

    async def test_soft_deleted_llm_config_is_reported_not_crashed(self):
        # get_config filters is_deleted, so a config removed after the chatbot
        # was saved comes back as None. Reachable in normal operation.
        config_service = AsyncMock()
        config_service.get_config.return_value = None
        chatbot = SimpleNamespace(llm_config_id=uuid.uuid4(), config=None)

        service = ChatInferenceService(llm_inference_config_service=config_service)

        with pytest.raises(ChatInferenceError):
            await service.resolve_llm(chatbot)

    async def test_unsupported_provider_is_surfaced_as_inference_error(self):
        config_service = AsyncMock()
        config_service.get_config.return_value = {
            'llm_model': 'some-model',
            'display_name': 'x',
            'type': 'not-a-provider',
            'api_key': 'k',
        }
        chatbot = SimpleNamespace(llm_config_id=uuid.uuid4(), config=None)

        service = ChatInferenceService(llm_inference_config_service=config_service)

        with pytest.raises(ChatInferenceError):
            await service.resolve_llm(chatbot)
