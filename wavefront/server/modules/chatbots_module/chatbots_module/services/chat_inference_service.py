from typing import Any, AsyncIterator, Optional

from common_module.log.logger import logger
from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai.llm import BaseLLM

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

    def __init__(self, llm_inference_config_service):
        self.llm_inference_config_service = llm_inference_config_service

    async def resolve_llm(self, chatbot: Chatbot) -> BaseLLM:
        """Build the chatbot's LLM, or raise ChatInferenceError.

        Public and separate from generate/stream on purpose. Async generators
        are lazy, so resolving inside `stream()` would not run until Starlette
        had already sent a 200 and the response headers -- a chatbot pointing at
        a deleted config would then report success and hide the error inside the
        event stream. Callers resolve first, while they can still choose a
        status code.
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
            return build_llm(llm_config, temperature)
        except ValueError as exc:
            raise ChatInferenceError(str(exc)) from exc

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
        """
        messages = self.build_messages(session, history)

        logger.info(
            f'Chat inference (streaming) for session={session.id} '
            f'messages={len(messages)}'
        )

        async for chunk in llm.stream(messages):
            content: Optional[str] = chunk.get('content') if chunk else None
            if content:
                yield content
