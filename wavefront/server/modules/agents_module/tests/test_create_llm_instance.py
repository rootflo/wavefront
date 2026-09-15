"""
Tests for AgentInferenceService._create_llm_instance parameter forwarding
"""

import pytest
from db_repo_module.models.llm_inference_config import LlmInferenceConfig

from agents_module.services.agent_inference_service import AgentInferenceService


@pytest.fixture
def service() -> AgentInferenceService:
    """The method under test only reads class state, so skip the DI wiring."""
    return object.__new__(AgentInferenceService)


def config(
    config_type: str, parameters: dict | None, **overrides
) -> LlmInferenceConfig:
    fields = {
        'llm_model': 'gpt-4.1-mini',
        'display_name': 'Test config',
        'api_key': 'test-key-123',
        'type': config_type,
        'base_url': 'https://example.invalid',
        'parameters': parameters,
    }
    fields.update(overrides)
    return LlmInferenceConfig(**fields)


class TestCreateLlmInstanceParameters:
    """Test cases for forwarding config parameters to the LLM constructors"""

    def test_openai_receives_every_parameter(self, service):
        """Everything the config UI collects should reach the request."""
        llm = service._create_llm_instance(
            config(
                'openai',
                {
                    'temperature': 0.3,
                    'max_completion_tokens': 500,
                    'top_p': 0.9,
                    'frequency_penalty': 0.5,
                    'presence_penalty': 0.25,
                    'seed': 42,
                    'service_tier': 'auto',
                },
            )
        )

        assert llm.temperature == 0.3
        assert llm.kwargs == {
            'max_completion_tokens': 500,
            'top_p': 0.9,
            'frequency_penalty': 0.5,
            'presence_penalty': 0.25,
            'seed': 42,
            'service_tier': 'auto',
        }

    def test_azure_api_version_configures_the_client(self, service):
        """It binds to the constructor argument, so it never reaches the body."""
        llm = service._create_llm_instance(
            config(
                'azure_openai',
                {
                    'api_version': '2024-10-21',
                    'temperature': 0.3,
                    'top_p': 0.9,
                },
                base_url='https://example.cognitiveservices.azure.com',
            )
        )

        assert llm.temperature == 0.3
        assert llm.kwargs == {'top_p': 0.9}
        assert llm.client._api_version == '2024-10-21'

    def test_anthropic_receives_its_parameters(self, service):
        """Test anthropic receives its parameters."""
        llm = service._create_llm_instance(
            config(
                'anthropic',
                {'temperature': 0.3, 'max_tokens': 500, 'top_p': 0.9, 'top_k': 5},
                llm_model='claude-3-5-sonnet-20240620',
            )
        )

        assert llm.temperature == 0.3
        assert llm.kwargs == {'max_tokens': 500, 'top_p': 0.9, 'top_k': 5}

    def test_gemini_receives_its_parameters(self, service):
        """Test gemini receives its parameters."""
        llm = service._create_llm_instance(
            config(
                'gemini',
                {'temperature': 0.3, 'max_tokens': 500, 'top_p': 0.9},
                llm_model='gemini-2.5-flash',
            )
        )

        assert llm.temperature == 0.3
        # Gemini renames the token limit when it builds its config
        assert llm._generation_config_kwargs({}) == {
            'max_output_tokens': 500,
            'top_p': 0.9,
        }

    def test_vllm_receives_its_parameters(self, service):
        """Test vllm receives its parameters."""
        llm = service._create_llm_instance(
            config(
                'vllm',
                {'temperature': 0.3, 'max_tokens': 500, 'top_p': 0.9},
                base_url='http://localhost:8000/v1',
            )
        )

        assert llm.temperature == 0.3
        assert llm.api_key == 'test-key-123'
        assert llm.kwargs == {'max_tokens': 500, 'top_p': 0.9}

    def test_null_parameters_are_dropped(self, service):
        """A null must not override the provider's own default."""
        llm = service._create_llm_instance(
            config('openai', {'temperature': None, 'top_p': 0.9, 'seed': None})
        )

        assert llm.temperature == 0.7
        assert llm.kwargs == {'top_p': 0.9}

    def test_missing_parameters_are_tolerated(self, service):
        """Test missing parameters are tolerated."""
        llm = service._create_llm_instance(config('openai', None))

        assert llm.temperature == 0.7
        assert llm.kwargs == {}

    def test_temperature_zero_survives(self, service):
        """Test temperature zero survives."""
        llm = service._create_llm_instance(config('openai', {'temperature': 0}))

        assert llm.temperature == 0

    def test_reserved_keys_cannot_collide(self, service):
        """A stale key the branch passes itself would be a duplicate kwarg."""
        llm = service._create_llm_instance(
            config(
                'openai',
                {'model': 'wrong', 'api_key': 'wrong', 'base_url': 'x', 'top_p': 0.9},
            )
        )

        assert llm.model == 'gpt-4.1-mini'
        assert llm.api_key == 'test-key-123'
        assert llm.kwargs == {'top_p': 0.9}

    def test_unsupported_type_still_raises(self, service):
        """Test unsupported type still raises."""
        with pytest.raises(ValueError, match='Unsupported LLM type: groq'):
            service._create_llm_instance(config('groq', {'temperature': 0.3}))
