"""Guardrails actually attach to a chatbot's LLM, and actually run on input.

Two failures this pins down, both of which look identical from outside --
traffic flows, nothing errors, and the settings page says "enforcing":

`resolve_llm` returning an unwrapped LLM. It is the single wrap point, so a
mistake there is not partial coverage, it is none.

`check_user_message` not reaching the engine. An earlier version imported the
stage as `from flo_ai.guardrails import BEFORE_MODEL`, which does not exist --
the name is `WorkflowStage.BEFORE_MODEL` -- inside a `try/except ImportError`
that swallowed it and returned. Every message passed. Asserting on the call
itself, rather than on the outcome for a blocked message, is what makes the
test fail instead of vacuously passing when nothing is evaluated.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flo_ai.guardrails import Principal, WorkflowStage
from flo_ai.llm.guarded_llm import GuardedLLM, GuardrailBlocked

from chatbots_module.services.chat_inference_service import ChatInferenceService
from common_module.utils.guardrails import guarded_llm


class _StubLlm:
    """Enough of BaseLLM for GuardedLLM to copy its attributes across."""

    model = 'stub-model'
    api_key = 'stub-key'
    temperature = 0.5
    kwargs: dict = {}


def _chatbot(namespace='acme', name='support-bot'):
    return SimpleNamespace(
        namespace=namespace, name=name, llm_config_id=uuid.uuid4(), config=None
    )


def _decision(blocked=False, transformed=False):
    # block_reasons is read by GuardrailBlocked's constructor, not by us.
    return SimpleNamespace(
        blocked=blocked,
        transformed=transformed,
        caller_message=lambda subject: f'refused-{subject}',
        operator_summary=lambda: 'adapter=stub',
        block_reasons=lambda: ['stub said no'],
    )


class TestGuardedLlm:
    def test_no_engine_leaves_the_llm_alone(self):
        # The celery worker and other entry points build LLMs without the
        # guardrails stack; that is unguarded, not broken.
        llm = _StubLlm()
        assert guarded_llm(llm, None, 'acme', 'support-bot') is llm

    def test_missing_namespace_leaves_the_llm_alone(self):
        # Policy resolves per namespace, so there is nothing to enforce.
        llm = _StubLlm()
        assert guarded_llm(llm, object(), None, 'support-bot') is llm

    def test_wrapping_binds_the_principal(self):
        llm = _StubLlm()
        engine = object()

        wrapped = guarded_llm(llm, engine, 'acme', 'support-bot', 'user-1')

        assert isinstance(wrapped, GuardedLLM)
        assert wrapped._inner_llm is llm
        assert wrapped._engine is engine
        assert wrapped._principal == Principal(
            namespace='acme', agent_id='support-bot', user_id='user-1'
        )

    def test_user_id_is_optional(self):
        # Agents have no end-user identity to bind; audit rows carry None.
        wrapped = guarded_llm(_StubLlm(), object(), 'acme', 'some-agent')

        assert wrapped._principal.user_id is None

    def test_wrapping_twice_returns_the_first_wrapper(self):
        # A second wrapper would evaluate every payload twice: the safety
        # provider is billed twice and each decision is logged two times.
        engine = object()
        once = guarded_llm(_StubLlm(), engine, 'acme', 'support-bot')

        assert guarded_llm(once, engine, 'acme', 'support-bot') is once

    def test_chat_does_not_opt_into_incremental_release(self):
        # A chat delta cannot be taken back once sent, so the wrapper must be
        # left unable to release before the whole reply has been cleared.
        wrapped = guarded_llm(_StubLlm(), object(), 'acme', 'support-bot')

        assert wrapped._supports_retract is False


class TestResolveLlmWrapping:
    async def _resolve(self, engine, namespace='acme'):
        config_service = AsyncMock()
        config_service.get_config.return_value = {
            'llm_model': 'gpt-4o',
            'display_name': 'x',
            'type': 'openai',
            'api_key': 'k',
        }
        service = ChatInferenceService(
            llm_inference_config_service=config_service, guardrails_engine=engine
        )
        return await service.resolve_llm(_chatbot(namespace=namespace), 'user-1')

    async def test_engine_present_returns_a_guarded_llm(self):
        assert isinstance(await self._resolve(object()), GuardedLLM)

    async def test_no_engine_returns_the_provider_client(self):
        assert not isinstance(await self._resolve(None), GuardedLLM)

    async def test_namespaceless_chatbot_is_not_guarded(self):
        assert not isinstance(await self._resolve(object(), namespace=None), GuardedLLM)


class TestCheckUserMessage:
    def _service(self, engine):
        return ChatInferenceService(
            llm_inference_config_service=AsyncMock(), guardrails_engine=engine
        )

    async def test_it_evaluates_before_model_against_the_engine(self):
        # The regression test for the swallowed-ImportError bug. Asserting the
        # call, not just the absence of a raise: a check that never runs also
        # never raises.
        engine = AsyncMock()
        engine.evaluate.return_value = _decision()

        await self._service(engine).check_user_message(
            _chatbot(), 'hello there', 'user-1'
        )

        engine.evaluate.assert_awaited_once_with(
            'hello there',
            principal=Principal(
                namespace='acme', agent_id='support-bot', user_id='user-1'
            ),
            stage=WorkflowStage.BEFORE_MODEL,
            destination='llm_provider',
        )

    async def test_a_blocked_message_raises_before_anything_is_written(self):
        engine = AsyncMock()
        decision = _decision(blocked=True)
        engine.evaluate.return_value = decision

        with pytest.raises(GuardrailBlocked) as raised:
            await self._service(engine).check_user_message(_chatbot(), 'bad', 'user-1')

        assert raised.value.decision is decision
        assert str(raised.value) == 'refused-request'

    async def test_a_transformed_message_is_allowed_through_unchanged(self):
        # Pins the asymmetry: at BEFORE_MODEL the redaction applies to the copy
        # sent to the provider and is not written back, so the thread keeps the
        # raw text the person actually typed. Acting on `transformed` here
        # would rewrite their own message under them.
        engine = AsyncMock()
        engine.evaluate.return_value = _decision(transformed=True)

        await self._service(engine).check_user_message(_chatbot(), 'card', 'user-1')

    async def test_no_engine_skips_the_check(self):
        await self._service(None).check_user_message(_chatbot(), 'hello', 'user-1')

    async def test_namespaceless_chatbot_skips_the_check(self):
        engine = AsyncMock()

        await self._service(engine).check_user_message(
            _chatbot(namespace=None), 'hello', 'user-1'
        )

        engine.evaluate.assert_not_awaited()
