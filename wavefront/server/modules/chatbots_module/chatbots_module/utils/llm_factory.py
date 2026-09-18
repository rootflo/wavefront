"""Build a flo_ai LLM from a stored LlmInferenceConfig."""

import os
from typing import Any, Optional

from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai.helpers.generation_params import normalize_generation_params
from flo_ai.llm import (
    Anthropic,
    AzureOpenAI,
    BaseLLM,
    Gemini,
    OllamaLLM,
    OpenAI,
    OpenAIVLLM,
)

# Passed explicitly below; a config carrying one would be a duplicate kwarg.
RESERVED_PARAMETERS = frozenset({'model', 'api_key', 'base_url', 'azure_endpoint'})

# Groq speaks the OpenAI protocol, so the OpenAI client covers it; it just needs
# pointing at Groq unless the config names its own endpoint.
GROQ_BASE_URL = 'https://api.groq.com/openai/v1'


def resolve_temperature(
    chatbot_config: Optional[dict[str, Any]],
) -> Optional[float]:
    """The chatbot's temperature override, or None to leave it alone.

    Only the chatbot is consulted. The LLM config's own temperature reaches the
    client through its `parameters` dict in build_llm, so reading it here as
    well would give one setting two code paths.

    Tests for key PRESENCE rather than truthiness: `temperature: 0` is a
    legitimate, commonly-used setting and is falsy, so
    `config.get('temperature') or fallback` would silently discard it.
    """
    if chatbot_config and 'temperature' in chatbot_config:
        return chatbot_config['temperature']
    return None


def build_llm(
    config: LlmInferenceConfig, temperature: Optional[float] = None
) -> BaseLLM:
    """Instantiate the flo_ai LLM described by `config`.

    Mirrors AgentInferenceService._create_llm_instance in agents_module
    (services/agent_inference_service.py). Duplicated rather than reused because
    that one is private to the service and takes no per-caller temperature.
    Keep the provider branches here in sync with it.
    """
    # Declared names (temperature, api_version) bind to the constructor
    # arguments; the rest ride through as **kwargs into the request body. Nulls
    # are dropped so the provider's own defaults still apply, and the token
    # limit is renamed to whatever this provider calls it -- a config created
    # for one provider and later pointed at another keeps the first one's key,
    # and OpenAI rejects a request carrying both `max_tokens` and
    # `max_completion_tokens`.
    llm_kwargs: dict[str, Any] = normalize_generation_params(
        {
            key: value
            for key, value in (config.parameters or {}).items()
            if key not in RESERVED_PARAMETERS
        },
        config.type,
    )

    # Applied after normalisation so the chatbot's own setting beats the one
    # stored on the shared LLM config.
    if temperature is not None:
        llm_kwargs['temperature'] = temperature

    # Empty rather than '' so the SDK falls back to its own default. Passed to
    # every provider that accepts one: a config pointing at LiteLLM, a gateway
    # or a self-hosted OpenAI-compatible endpoint would otherwise reach the
    # vendor's public API instead, with no error to show it.
    base_url = config.base_url or None

    if config.type == 'openai':
        return OpenAI(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=base_url,
            **llm_kwargs,
        )
    elif config.type == 'groq':
        return OpenAI(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=base_url or GROQ_BASE_URL,
            **llm_kwargs,
        )
    elif config.type == 'azure_openai':
        # Azure is not OpenAI-with-a-base_url: it needs a deployment endpoint
        # and an api_version, and the client will not build without one, so
        # fall back to the env.
        api_version = llm_kwargs.get('api_version') or os.getenv(
            'AZURE_OPENAI_API_VERSION'
        )
        if api_version:
            llm_kwargs['api_version'] = api_version

        return AzureOpenAI(
            model=config.llm_model,
            api_key=config.api_key,
            azure_endpoint=config.base_url,
            **llm_kwargs,
        )
    elif config.type == 'anthropic':
        return Anthropic(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=base_url,
            **llm_kwargs,
        )
    elif config.type == 'gemini':
        return Gemini(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=base_url,
            **llm_kwargs,
        )
    elif config.type == 'ollama':
        # Only when set: OllamaLLM defaults it to localhost and calls .rstrip()
        # on it, so an explicit None is an AttributeError.
        ollama_kwargs = dict(llm_kwargs)
        if base_url:
            ollama_kwargs['base_url'] = base_url
        return OllamaLLM(model=config.llm_model, **ollama_kwargs)
    elif config.type == 'vllm':
        return OpenAIVLLM(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=config.base_url,
            **llm_kwargs,
        )
    else:
        raise ValueError(f'Unsupported LLM type: {config.type}')
