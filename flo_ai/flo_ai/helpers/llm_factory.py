"""
LLM Factory - Centralized LLM creation from configuration.

This module provides a unified factory function for creating LLM instances
from configuration models, supporting all providers in the flo_ai ecosystem.
"""

import os
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from flo_ai.llm import BaseLLM

from flo_ai.helpers.generation_params import (
    CANONICAL_GENERATION_PARAMS,
    merge_generation_params,
)
from flo_ai.models.agent import LLMConfigModel
from flo_ai.utils.logger import logger


class LLMFactory:
    """Factory class for creating LLM instances from configuration."""

    # Providers whose wrapper hands unrecognised kwargs to the SDK client,
    # where `timeout` is a client option. The others would send it as a
    # generation param, which is not what a request timeout is.
    _TIMEOUT_CAPABLE_PROVIDERS = {
        'openai',
        'anthropic',
        'claude',
        'openai_vllm',
        'azure_openai',
    }

    SUPPORTED_PROVIDERS = {
        'openai',
        'anthropic',
        'gemini',
        'ollama',
        'vertexai',
        'rootflo',
        'openai_vllm',
        'azure_openai',
    }

    # LLMConfigModel accepts these spellings, so the factory has to dispatch on
    # the provider they name rather than rejecting them as unsupported.
    PROVIDER_ALIASES = {'claude': 'anthropic', 'google': 'gemini'}

    @staticmethod
    def create_llm(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
        """Create an LLM instance from model configuration.

        Args:
            model_config: LLMConfigModel instance containing model configuration
            **kwargs: Additional parameters that override config and env vars:
                - base_url: Override base URL
                - For RootFlo: app_key, app_secret, issuer, audience, access_token

        Returns:
            BaseLLM: Configured LLM instance

        Raises:
            ValueError: If provider is unsupported or required parameters are missing
        """
        provider = model_config.provider.lower()
        provider = LLMFactory.PROVIDER_ALIASES.get(provider, provider)

        if provider not in LLMFactory.SUPPORTED_PROVIDERS:
            raise ValueError(
                f'Unsupported model provider: {provider}. '
                f'Supported providers: {", ".join(sorted(LLMFactory.SUPPORTED_PROVIDERS))}'
            )

        if provider == 'rootflo':
            return LLMFactory._create_rootflo_llm(model_config, **kwargs)
        elif provider == 'vertexai':
            return LLMFactory._create_vertexai_llm(model_config, **kwargs)
        elif provider == 'openai_vllm':
            return LLMFactory._create_openai_vllm_llm(model_config, **kwargs)
        elif provider == 'azure_openai':
            return LLMFactory._create_azure_openai_llm(model_config, **kwargs)
        else:
            return LLMFactory._create_standard_llm(provider, model_config, **kwargs)

    @staticmethod
    def _model_block_params(
        provider: str, model_config: LLMConfigModel, **kwargs
    ) -> Dict[str, Any]:
        """The generation and client params a `model:` block can carry.

        Every provider's wrapper is built through this, so that a field set in
        the block reaches all of them or none. Read per-provider instead, it
        was honoured for two of the eight - and a caller of the factory who did
        not go through a builder got the wrapper's default 0.7 with nothing to
        say the value had been dropped.

        `max_tokens` is translated to whatever `provider` calls its token limit.
        `timeout` is a client option, so it is only passed to the wrappers that
        route unrecognised kwargs to their SDK client; elsewhere it would be
        sent as a generation param, and the request would carry a meaningless
        field instead of having a deadline.

        Args:
            provider: Provider name from the model block
            model_config: The model block
            kwargs: Caller overrides, which win over the model block

        Returns:
            Constructor kwargs for the provider's wrapper. A field the block
            leaves unset is absent, so the wrapper's own default applies - for
            rootflo that is what lets the fetched configuration's value win.
        """
        # The block itself can only express a token limit; the rest of the
        # canonical set arrives as caller kwargs. Both go through one merge so
        # a caller's value wins and the token limit is named once.
        caller_params = {
            key: kwargs[key] for key in CANONICAL_GENERATION_PARAMS if key in kwargs
        }
        params = merge_generation_params(
            {'max_tokens': model_config.max_tokens}, caller_params, provider
        )

        # `.get` with a fallback rather than `or`: 0.0 is a valid temperature
        # and must not be read as unset.
        temperature = kwargs.get('temperature', model_config.temperature)
        if temperature is not None:
            params['temperature'] = temperature

        timeout = kwargs.get('timeout', model_config.timeout)
        if timeout is not None:
            if provider in LLMFactory._TIMEOUT_CAPABLE_PROVIDERS:
                params['timeout'] = timeout
            else:
                logger.warning(
                    f'Ignoring model.timeout: {provider} does not take a request '
                    'timeout through its configuration.'
                )

        return params

    @staticmethod
    def _create_standard_llm(
        provider: str, model_config: LLMConfigModel, **kwargs
    ) -> 'BaseLLM':
        """Create standard LLM instances (OpenAI, Anthropic, Gemini, Ollama)."""
        from flo_ai.llm import OpenAI, Anthropic, Gemini, OllamaLLM

        model_name = model_config.name
        if not model_name:
            raise ValueError(
                f'{provider.title()} provider requires "name" parameter in model configuration'
            )

        provider_map = {
            'openai': OpenAI,
            'anthropic': Anthropic,
            'gemini': Gemini,
            'ollama': OllamaLLM,
        }

        llm_kwargs = LLMFactory._model_block_params(provider, model_config, **kwargs)

        # Priority: kwargs > model_config > the wrapper's own default. Passed
        # only when set: OllamaLLM defaults it to localhost and calls .rstrip()
        # on whatever it is given, so an explicit None is an AttributeError.
        base_url = kwargs.get('base_url') or model_config.base_url
        if base_url:
            llm_kwargs['base_url'] = base_url

        # Credentials from the model block, so an agent built from YAML is not
        # limited to whatever the process environment happens to carry.
        api_key = kwargs.get('api_key') or model_config.api_key
        if api_key:
            llm_kwargs['api_key'] = api_key

        llm_class = provider_map[provider]
        return llm_class(model=model_name, **llm_kwargs)

    @staticmethod
    def _create_vertexai_llm(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
        """Create VertexAI LLM instance with project and location."""
        from flo_ai.llm import VertexAI

        model_name = model_config.name
        if not model_name:
            raise ValueError(
                'VertexAI provider requires "name" parameter in model configuration'
            )

        # Get VertexAI-specific parameters
        project = kwargs.get('project') or model_config.project
        location = kwargs.get('location') or model_config.location or 'asia-south1'
        base_url = kwargs.get('base_url') or model_config.base_url

        if not project:
            raise ValueError(
                'VertexAI provider requires "project" parameter. '
                'Provide it in model_config or as a kwarg.'
            )

        if not base_url:
            raise ValueError(
                'VertexAI provider requires "base_url" parameter. '
                'Provide it in model_config or as a kwarg.'
            )

        return VertexAI(
            model=model_name,
            project=project,
            location=location,
            base_url=str(base_url),
            **LLMFactory._model_block_params('gemini', model_config, **kwargs),
        )

    @staticmethod
    def _create_openai_vllm_llm(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
        """Create OpenAI vLLM instance with base_url handling."""
        from flo_ai.llm import OpenAIVLLM

        model_name = model_config.name
        if not model_name:
            raise ValueError(
                'openai_vllm provider requires "name" parameter in model configuration'
            )

        # Priority: kwargs > model_config > None
        base_url = kwargs.get('base_url') or model_config.base_url
        if not base_url:
            raise ValueError(
                'openai_vllm provider requires "base_url" parameter. '
                'Provide it in model_config or as a kwarg.'
            )

        # Optional parameters
        api_key = kwargs.get('api_key') or model_config.api_key
        if not api_key:
            raise ValueError(
                'openai_vllm provider requires "api_key" parameter. '
                'Provide it in model_config or as a kwarg.'
            )
        return OpenAIVLLM(
            model=model_name,
            base_url=str(base_url),
            api_key=str(api_key),
            **LLMFactory._model_block_params('openai_vllm', model_config, **kwargs),
        )

    @staticmethod
    def _create_azure_openai_llm(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
        """Create Azure OpenAI LLM instance with endpoint and API version."""
        from flo_ai.llm import AzureOpenAI

        model_name = model_config.name
        if not model_name:
            raise ValueError('azure_openai provider requires "name" parameter')

        # Endpoint and API version
        azure_endpoint = (
            kwargs.get('azure_endpoint')
            or model_config.azure_endpoint
            or os.getenv('AZURE_OPENAI_ENDPOINT')
        )
        if not azure_endpoint:
            raise ValueError(
                'azure_openai configuration incomplete. Missing required parameter: '
                'azure_endpoint. Provide it in model_config, as a kwarg, or via '
                'AZURE_OPENAI_ENDPOINT environment variable.'
            )

        api_key = (
            kwargs.get('api_key')
            or model_config.api_key
            or os.getenv('AZURE_OPENAI_API_KEY')
        )
        if not api_key:
            raise ValueError(
                'azure_openai configuration incomplete. Missing required parameter: '
                'api_key. Provide it in model_config, as a kwarg, or via '
                'AZURE_OPENAI_API_KEY environment variable.'
            )

        api_version = (
            kwargs.get('azure_api_version')
            or model_config.azure_api_version
            or os.getenv('AZURE_OPENAI_API_VERSION')
            or '2024-12-01-preview'
        )

        return AzureOpenAI(
            model=model_name,
            api_key=str(api_key),
            azure_endpoint=str(azure_endpoint),
            api_version=str(api_version),
            **LLMFactory._model_block_params('azure_openai', model_config, **kwargs),
        )

    @staticmethod
    def _create_rootflo_llm(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
        """Create RootFlo LLM instance with authentication."""
        from flo_ai.llm import RootFloLLM

        model_id = model_config.model_id
        if not model_id:
            raise ValueError(
                'RootFlo provider requires "model_id" in model configuration'
            )

        # Gather RootFlo parameters from kwargs or environment
        base_url = (
            kwargs.get('base_url')
            or model_config.base_url
            or os.getenv('ROOTFLO_BASE_URL')
        )
        app_key = kwargs.get('app_key') or os.getenv('ROOTFLO_APP_KEY')
        app_secret = kwargs.get('app_secret') or os.getenv('ROOTFLO_APP_SECRET')
        issuer = kwargs.get('issuer') or os.getenv('ROOTFLO_ISSUER')
        audience = kwargs.get('audience') or os.getenv('ROOTFLO_AUDIENCE')
        access_token = kwargs.get('access_token')  # Optional, from kwargs only

        # Access token flow - only needs base_url
        if not base_url:
            raise ValueError(
                'RootFlo configuration incomplete. Missing required parameter: base_url. '
                'Provide it in model_config, as a kwarg, or via ROOTFLO_BASE_URL environment variable.'
            )

        # temperature is absent from the params when the model block does not
        # specify one, so the fetched LlmInferenceConfig's own value applies
        # rather than RootFloLLM's constructor default overriding it.
        return RootFloLLM(
            base_url=str(base_url),
            model_id=model_id,
            app_key=app_key,
            app_secret=app_secret,
            issuer=issuer,
            audience=audience,
            access_token=access_token,
            **LLMFactory._model_block_params('rootflo', model_config, **kwargs),
        )


# Convenience function for direct import
def create_llm_from_config(model_config: LLMConfigModel, **kwargs) -> 'BaseLLM':
    """
    Convenience function to create an LLM instance from configuration.

    This is a wrapper around LLMFactory.create_llm() for easier imports.

    Args:
        model_config: LLMConfigModel instance containing model configuration
        **kwargs: Additional parameters that override config and env vars

    Returns:
        BaseLLM: Configured LLM instance

    See LLMFactory.create_llm() for detailed documentation.
    """
    return LLMFactory.create_llm(model_config, **kwargs)
