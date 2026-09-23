from typing import Any, AsyncIterator, Optional

from common_module.log.logger import logger
from common_module.utils.guardrails import guarded_llm
from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai.guardrails import Principal, WorkflowStage, is_control_chunk
from flo_ai.llm import BaseLLM
from flo_ai.llm.guarded_llm import GuardrailBlocked

from chatbots_module.utils.constants import ROLE_SYSTEM
from chatbots_module.utils.llm_factory import build_llm, resolve_temperature


class ChatInferenceError(Exception):
    pass


class ChatInferenceService:
    """Runs a chat turn against the chatbot's configured model.

    v1 chatbots have no tools, so this calls the LLM directly instead of going
    through flo_ai's AgentBuilder. An Agent carries its own conversation state
    (`add_to_history`) and would have to be rebuilt per request anyway, so
    wrapping one here would add a layer without adding a capability. Stored
    messages already have the shape every flo_ai LLM expects.
    """

    def __init__(self, llm_inference_config_service, guardrails_engine=None):
        self.llm_inference_config_service = llm_inference_config_service
        self.guardrails_engine = guardrails_engine

    async def resolve_llm(
        self, chatbot: Chatbot, user_id: Optional[str] = None
    ) -> BaseLLM:
        """Build the chatbot's LLM, or raise ChatInferenceError.

        Public and separate from generate/stream on purpose. Async generators
        are lazy, so resolving inside `stream()` would not run until Starlette
        had already sent a 200 and the response headers -- a chatbot pointing at
        a deleted config would then report success and hide the error inside the
        event stream. Callers resolve first, while they can still choose a
        status code.

        This is also the single place guardrails are attached, for the same
        reason `apply_guardrails` wraps after `build()`: wrapping the one object
        every turn goes through does not depend on anyone downstream
        remembering to. `generate` and `stream` are deliberately left taking an
        already-wrapped llm.

        A fresh LLM is built per call, which is what makes it safe to bind
        `user_id` into the principal here. If this ever grows a cache keyed by
        chatbot, drop `user_id` at the same time -- a reused wrapper would
        attribute one person's turns to whoever built it first.
        """
        config_dict = await self.llm_inference_config_service.get_config(
            chatbot.llm_config_id
        )
        if not config_dict:
            # Reachable in normal operation: the config is validated when the
            # chatbot is saved, but it can be soft-deleted afterwards.
            raise ChatInferenceError(
                f'LLM inference configuration not found: {chatbot.llm_config_id}'
            )

        llm_config = LlmInferenceConfig(**config_dict)
        # Only the chatbot's override is resolved here; the config's own
        # temperature reaches the client through its `parameters` in build_llm.
        temperature = resolve_temperature(chatbot.config)

        try:
            llm = build_llm(llm_config, temperature)
        except ValueError as exc:
            raise ChatInferenceError(str(exc)) from exc

        return guarded_llm(
            llm,
            self.guardrails_engine,
            chatbot.namespace,
            chatbot.name,
            user_id,
        )

    async def check_user_message(
        self,
        chatbot: Chatbot,
        content: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Evaluate a just-typed message, raising GuardrailBlocked if refused.

        `GuardedLLM` already checks inbound content, but it does so on the way
        to the provider -- by which point the route has committed the user's
        message. A refused turn would be stored anyway, and every retry would
        store it again. Checking here keeps the write out of a turn that policy
        will not answer, and it is the only point at which the streaming path
        can still choose a status code: once `StreamingResponse` is returned
        the headers are gone.

        Blocks only. A transform is deliberately ignored: at BEFORE_MODEL it
        applies to the copy sent to the provider and is not written back, so
        the thread keeps the raw text the person actually typed while the
        provider sees the redacted one.

        The second evaluation this implies is close to free -- the verdict
        cache is keyed on (namespace, stage, policy version, content), so
        `GuardedLLM` finds this verdict and is deliberately neither logged nor
        audited again. The exception is an error verdict, which is never
        cached: during a safety-provider outage under FAIL_OPEN a turn costs
        two adapter attempts instead of one.
        """
        if self.guardrails_engine is None or not chatbot.namespace:
            return

        decision = await self.guardrails_engine.evaluate(
            content,
            principal=Principal(
                namespace=chatbot.namespace,
                agent_id=chatbot.name,
                user_id=user_id,
            ),
            stage=WorkflowStage.BEFORE_MODEL,
            destination='llm_provider',
        )

        if decision.blocked:
            logger.warning(
                f'Guardrail blocked a chat message before it was stored '
                f'[ns={chatbot.namespace}, chatbot={chatbot.name}] '
                f'{decision.operator_summary()}'
            )
            raise GuardrailBlocked(decision.caller_message('request'), decision)

    @staticmethod
    def build_messages(
        session: ChatSession, history: list[ChatMessage]
    ) -> list[dict[str, Any]]:
        """System prompt first, then the thread in send order."""
        messages: list[dict[str, Any]] = [
            {'role': ROLE_SYSTEM, 'content': session.system_prompt_snapshot}
        ]
        messages.extend(
            {'role': message.role, 'content': message.content} for message in history
        )
        return messages

    async def generate(
        self,
        llm: BaseLLM,
        session: ChatSession,
        history: list[ChatMessage],
    ) -> str:
        """Run one turn. `llm` comes from resolve_llm()."""
        messages = self.build_messages(session, history)

        logger.info(f'Chat inference for session={session.id} messages={len(messages)}')

        response = await llm.generate(messages)
        return llm.get_message_content(response)

    async def stream(
        self,
        llm: BaseLLM,
        session: ChatSession,
        history: list[ChatMessage],
    ) -> AsyncIterator[str]:
        """Yield content deltas. `llm` comes from resolve_llm().

        Every provider's stream() yields `{'content': <delta>}` -- verified for
        openai, azure_openai, anthropic, gemini, ollama and vllm -- so keying on
        that is safe across the set build_llm() can return.

        A guarded stream can also release incrementally and then *retract* what
        it already sent, replacing it. This consumer cannot do that: a delta
        yielded here has been appended to the client's transcript and there is
        no frame to take it back. So chat never calls `declare_retract_support`
        -- which is what makes `GuardedLLM` downgrade incremental release to
        buffering, where nothing is emitted before the whole reply has been
        cleared and a retract can therefore never arise.

        The guard below is for if that stops being true. A control chunk
        reaching this loop means the invariant broke somewhere above, and
        letting it fall through to `.get('content')` would drop it in silence,
        leaving withdrawn text on the user's screen. To support incremental
        release properly, add a retract frame to the SSE protocol and follow
        `agents_module.services.agent_stream_events._apply_control`.
        """
        messages = self.build_messages(session, history)

        logger.info(
            f'Chat inference (streaming) for session={session.id} '
            f'messages={len(messages)}'
        )

        async for chunk in llm.stream(messages):
            if is_control_chunk(chunk):
                logger.warning(
                    f'Discarding a guardrail control chunk on the chat stream '
                    f'for session={session.id}; this path does not implement '
                    f'retract and should never have been sent one'
                )
                continue
            content: Optional[str] = chunk.get('content') if chunk else None
            if content:
                yield content
