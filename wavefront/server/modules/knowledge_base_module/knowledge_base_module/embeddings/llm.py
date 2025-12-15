from typing import Any, Optional
from flo_ai.helpers.llm_factory import LLMFactory
from flo_ai.llm import Gemini
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai.models.agent import LLMConfigModel


class LLMModelFunc:
    def _create_llm_instance(self, config: LlmInferenceConfig):
        """
        Create LLM instance based on configuration

        Args:
            config: LLM inference configuration

        Returns:
            LLM instance
        """
        config = LLMConfigModel(
            provider='rootflo',
            model_id=config.id,
        )
        return LLMFactory.create_llm(config)

    async def generate_response(
        self,
        query,
        sys_prompt,
        model,
        llm_config: Optional[LlmInferenceConfig] = None,
    ):
        """
        Generate LLM response

        Args:
            query: User query
            sys_prompt: System prompt
            conversation_history: Conversation history
            model: Model name (used if llm_config not provided)
            llm_config: Optional LLM inference configuration

        Returns:
            Generated response content
        """
        messages: list[dict[str, Any]] = []
        if sys_prompt:
            messages.append({'role': 'system', 'content': sys_prompt})
        messages.append({'role': 'user', 'content': query})

        # Use config-based LLM if provided, otherwise fall back to default Gemini
        if llm_config:
            llm = self._create_llm_instance(llm_config)
        else:
            llm = Gemini(
                model=model,
                temperature=0.7,
            )

        response = await llm.generate(messages)
        return llm.get_message_content(response)
