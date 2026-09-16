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
        with pytest.raises(ValueError, match='Unsupported LLM type: cohere'):
            service._create_llm_instance(config('cohere', {'temperature': 0.3}))


class TestGroq:
    """Groq is a valid config type and has a full parameter block in the UI."""

    def test_it_builds(self, service):
        """It used to raise, so a groq config could be saved but never used."""
        llm = service._create_llm_instance(
            config('groq', {'temperature': 0.3, 'top_p': 0.9}, base_url=None)
        )

        assert llm.temperature == 0.3
        assert llm.kwargs == {'top_p': 0.9}

    def test_it_points_at_groq_by_default(self, service):
        """Test it points at groq by default."""
        llm = service._create_llm_instance(config('groq', None, base_url=None))

        assert str(llm.client.base_url).startswith('https://api.groq.com')

    def test_a_configured_base_url_wins(self, service):
        """Test a configured base url wins."""
        llm = service._create_llm_instance(
            config('groq', None, base_url='https://gateway.invalid/v1')
        )

        assert str(llm.client.base_url).startswith('https://gateway.invalid')

    def test_the_token_limit_is_openai_spelled(self, service):
        """Test the token limit is openai spelled."""
        llm = service._create_llm_instance(config('groq', {'max_tokens': 500}))

        assert llm.kwargs == {'max_completion_tokens': 500}


class TestBaseUrl:
    """A config's base_url has to reach every provider that accepts one.

    It was passed only for azure, ollama and vllm, so a config pointing at
    LiteLLM, a gateway or a self-hosted OpenAI-compatible endpoint reached the
    vendor's public API instead - a silent misroute with nothing to show it.
    """

    def test_openai(self, service):
        """Test openai."""
        llm = service._create_llm_instance(
            config('openai', None, base_url='https://gateway.invalid/v1')
        )

        assert str(llm.client.base_url).startswith('https://gateway.invalid')

    def test_anthropic(self, service):
        """Test anthropic."""
        llm = service._create_llm_instance(
            config(
                'anthropic',
                None,
                llm_model='claude-3-5-sonnet-20240620',
                base_url='https://gateway.invalid',
            )
        )

        assert str(llm.client.base_url).startswith('https://gateway.invalid')

    def test_gemini(self, service):
        """Test gemini."""
        llm = service._create_llm_instance(
            config(
                'gemini',
                None,
                llm_model='gemini-2.5-flash',
                base_url='https://gateway.invalid',
            )
        )

        assert llm.client._api_client._http_options.base_url == (
            'https://gateway.invalid'
        )

    def test_an_empty_base_url_falls_back_to_the_sdk_default(self, service):
        """A stored '' must not be sent as the endpoint."""
        llm = service._create_llm_instance(config('openai', None, base_url=''))

        assert str(llm.client.base_url).startswith('https://api.openai.com')

    def test_ollama_keeps_its_own_default(self, service):
        """Passing None would be an AttributeError on None.rstrip('/')."""
        llm = service._create_llm_instance(
            config('ollama', None, llm_model='llama2', base_url=None)
        )

        assert llm.base_url == 'http://localhost:11434'


class TestTokenLimitIsNamedForTheProvider:
    """One canonical config field, one spelling per provider."""

    def test_openai(self, service):
        """Test openai."""
        llm = service._create_llm_instance(config('openai', {'max_tokens': 500}))

        assert llm.kwargs == {'max_completion_tokens': 500}

    def test_the_rejected_pair_collapses(self, service):
        """`'max_tokens' and 'max_completion_tokens' at the same time` is a 400.

        A config created as anthropic or vllm stores `max_tokens`; switched to
        openai and given a completion limit, it carried both.
        """
        llm = service._create_llm_instance(
            config('openai', {'max_tokens': 500, 'max_completion_tokens': 800})
        )

        assert llm.kwargs == {'max_completion_tokens': 800}

    def test_anthropic_keeps_its_own_spelling(self, service):
        """Test anthropic keeps its own spelling."""
        llm = service._create_llm_instance(
            config(
                'anthropic',
                {'max_tokens': 500},
                llm_model='claude-3-5-sonnet-20240620',
            )
        )

        assert llm.kwargs == {'max_tokens': 500}

    def test_a_stale_openai_limit_is_carried_over_for_anthropic(self, service):
        """The value is what the user last set, so it should still apply."""
        llm = service._create_llm_instance(
            config(
                'anthropic',
                {'max_completion_tokens': 800},
                llm_model='claude-3-5-sonnet-20240620',
            )
        )

        assert llm.kwargs == {'max_tokens': 800}

    def test_ollama(self, service):
        """Ollama calls it num_predict, and reads it from `options`."""
        llm = service._create_llm_instance(
            config('ollama', {'max_tokens': 500}, llm_model='llama2')
        )

        assert llm.kwargs == {'num_predict': 500}
        assert llm._request_payload('hi')['options']['num_predict'] == 500
