"""
LLM Factory - Centralized LLM creation from configuration.

This module provides a unified factory function for creating LLM instances
from configuration models, supporting all providers in the flo_ai ecosystem.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flo_ai.llm import BaseLLM

from flo_ai.models.agent import LLMConfigModel


class LLMFactory:
    """Factory class for creating LLM instances from configuration."""

    SUPPORTED_PROVIDERS = {
        'openai',
        'anthropic',
        'gemini',
        'ollama',
        'vertexai',
        'rootflo',
        'openai_vllm',
    }

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
        else:
            return LLMFactory._create_standard_llm(provider, model_config, **kwargs)

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

        # Priority: kwargs > model_config > None
        base_url = kwargs.get('base_url') or model_config.base_url

        provider_map = {
            'openai': OpenAI,
            'anthropic': Anthropic,
            'gemini': Gemini,
            'ollama': OllamaLLM,
        }

        llm_class = provider_map[provider]
        return llm_class(model=model_name, base_url=base_url)

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
        temperature = kwargs.get(
            'temperature',
            model_config.temperature if model_config.temperature is not None else 0.7,
        )

        return OpenAIVLLM(
            model=model_name,
            base_url=str(base_url),
            api_key=str(api_key),
            temperature=temperature,
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

        return RootFloLLM(
            base_url=str(base_url),
            model_id=model_id,
            app_key=app_key,
            app_secret=app_secret,
            issuer=issuer,
            audience=audience,
            access_token=access_token,
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
