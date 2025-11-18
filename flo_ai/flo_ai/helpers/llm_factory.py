"""
LLM Factory - Centralized LLM creation from configuration.

This module provides a unified factory function for creating LLM instances
from configuration dictionaries, supporting all providers in the flo_ai ecosystem.
"""

import os
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from flo_ai.llm import BaseLLM


class LLMFactory:
    """Factory class for creating LLM instances from configuration."""

    SUPPORTED_PROVIDERS = {
        'openai',
        'anthropic',
        'gemini',
        'ollama',
        'vertexai',
        'rootflo',
    }

    @staticmethod
    def create_llm(model_config: Dict[str, Any], **kwargs) -> 'BaseLLM':
        """Create an LLM instance from model configuration.

        Args:
            model_config: Dictionary containing model configuration with keys:
                - provider (str): LLM provider name (default: 'openai')
                - name (str): Model name (required for most providers)
                - base_url (str, optional): Custom base URL
                - model_id (str): For RootFlo provider
                - project (str): For VertexAI provider
                - location (str): For VertexAI provider (default: 'asia-south1')
            **kwargs: Additional parameters that override config and env vars:
                - base_url: Override base URL
                - For RootFlo: app_key, app_secret, issuer, audience, access_token

        Returns:
            BaseLLM: Configured LLM instance

        Raises:
            ValueError: If provider is unsupported or required parameters are missing

        Examples:
            >>> # OpenAI
            >>> llm = LLMFactory.create_llm({'provider': 'openai', 'name': 'gpt-4'})

            >>> # VertexAI with project
            >>> llm = LLMFactory.create_llm({
            ...     'provider': 'vertexai',
            ...     'name': 'gemini-pro',
            ...     'project': 'my-project',
            ...     'location': 'us-central1'
            ... })

            >>> # RootFlo with auth
            >>> llm = LLMFactory.create_llm(
            ...     {'provider': 'rootflo', 'model_id': 'model-123'},
            ...     app_key='key', app_secret='secret', issuer='iss', audience='aud'
            ... )
        """
        provider = model_config.get('provider', 'openai').lower()

        if provider not in LLMFactory.SUPPORTED_PROVIDERS:
            raise ValueError(
                f'Unsupported model provider: {provider}. '
                f'Supported providers: {", ".join(sorted(LLMFactory.SUPPORTED_PROVIDERS))}'
            )

        if provider == 'rootflo':
            return LLMFactory._create_rootflo_llm(model_config, **kwargs)
        elif provider == 'vertexai':
            return LLMFactory._create_vertexai_llm(model_config, **kwargs)
        else:
            return LLMFactory._create_standard_llm(provider, model_config, **kwargs)

    @staticmethod
    def _create_standard_llm(
        provider: str, model_config: Dict[str, Any], **kwargs
    ) -> 'BaseLLM':
        """Create standard LLM instances (OpenAI, Anthropic, Gemini, Ollama)."""
        from flo_ai.llm import OpenAI, Anthropic, Gemini, OllamaLLM

        model_name = model_config.get('name')
        if not model_name:
            raise ValueError(
                f'{provider.title()} provider requires "name" parameter in model configuration'
            )

        # Priority: kwargs > model_config > None
        base_url = kwargs.get('base_url') or model_config.get('base_url')

        provider_map = {
            'openai': OpenAI,
            'anthropic': Anthropic,
            'gemini': Gemini,
            'ollama': OllamaLLM,
        }

        llm_class = provider_map[provider]
        return llm_class(model=model_name, base_url=base_url)

    @staticmethod
    def _create_vertexai_llm(model_config: Dict[str, Any], **kwargs) -> 'BaseLLM':
        """Create VertexAI LLM instance with project and location."""
        from flo_ai.llm import VertexAI

        model_name = model_config.get('name')
        if not model_name:
            raise ValueError(
                'VertexAI provider requires "name" parameter in model configuration'
            )

        # Get VertexAI-specific parameters
        project = kwargs.get('project') or model_config.get('project')
        location = kwargs.get('location') or model_config.get('location', 'asia-south1')
        base_url = kwargs.get('base_url') or model_config.get('base_url')

        if not project:
            raise ValueError(
                'VertexAI provider requires "project" parameter. '
                'Provide it in model_config or as a kwarg.'
            )

        return VertexAI(
            model=model_name,
            project=project,
            location=location,
            base_url=base_url,
        )

    @staticmethod
    def _create_rootflo_llm(model_config: Dict[str, Any], **kwargs) -> 'BaseLLM':
        """Create RootFlo LLM instance with authentication."""
        from flo_ai.llm import RootFloLLM

        model_id = model_config.get('model_id')
        if not model_id:
            raise ValueError(
                'RootFlo provider requires "model_id" in model configuration'
            )

        # Gather RootFlo parameters from kwargs or environment
        base_url = (
            kwargs.get('base_url')
            or model_config.get('base_url')
            or os.getenv('ROOTFLO_BASE_URL')
        )
        app_key = kwargs.get('app_key') or os.getenv('ROOTFLO_APP_KEY')
        app_secret = kwargs.get('app_secret') or os.getenv('ROOTFLO_APP_SECRET')
        issuer = kwargs.get('issuer') or os.getenv('ROOTFLO_ISSUER')
        audience = kwargs.get('audience') or os.getenv('ROOTFLO_AUDIENCE')
        access_token = kwargs.get('access_token')  # Optional, from kwargs only

        # Validate required parameters based on auth method
        if not access_token:
            # JWT auth flow - requires all parameters
            required_params = {
                'base_url': base_url,
                'app_key': app_key,
                'app_secret': app_secret,
                'issuer': issuer,
                'audience': audience,
            }
            missing = [k for k, v in required_params.items() if not v]

            if missing:
                raise ValueError(
                    f'RootFlo configuration incomplete. Missing required parameters: {", ".join(missing)}. '
                    f'These can be provided via kwargs or environment variables '
                    f'(ROOTFLO_BASE_URL, ROOTFLO_APP_KEY, ROOTFLO_APP_SECRET, ROOTFLO_ISSUER, ROOTFLO_AUDIENCE).'
                )
        else:
            # Access token flow - only needs base_url and app_key
            required_params = {
                'base_url': base_url,
                'app_key': app_key,
            }
            missing = [k for k, v in required_params.items() if not v]

            if missing:
                raise ValueError(
                    f'RootFlo configuration incomplete. Missing required parameters: {", ".join(missing)}. '
                    f'These can be provided via kwargs or environment variables '
                    f'(ROOTFLO_BASE_URL, ROOTFLO_APP_KEY).'
                )

        return RootFloLLM(
            base_url=base_url,
            model_id=model_id,
            app_key=app_key,
            app_secret=app_secret,
            issuer=issuer,
            audience=audience,
            access_token=access_token,
        )


# Convenience function for direct import
def create_llm_from_config(model_config: Dict[str, Any], **kwargs) -> 'BaseLLM':
    """
    Convenience function to create an LLM instance from configuration.

    This is a wrapper around LLMFactory.create_llm() for easier imports.

    Args:
        model_config: Dictionary containing model configuration
        **kwargs: Additional parameters that override config and env vars

    Returns:
        BaseLLM: Configured LLM instance

    See LLMFactory.create_llm() for detailed documentation.
    """
    return LLMFactory.create_llm(model_config, **kwargs)
