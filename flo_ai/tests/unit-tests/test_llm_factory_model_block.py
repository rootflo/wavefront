"""
Tests for LLMFactory building an LLM from a YAML `model:` block.

The standard path passed the model name and base_url and nothing else, so an
agent built from a model block took its credentials from the process
environment, `max_tokens` and `timeout` were read by nothing at all, and an
ollama block with no base_url crashed on `None.rstrip('/')` instead of falling
back to the documented localhost default.
"""

import pytest

from flo_ai.helpers.llm_factory import LLMFactory
from flo_ai.models.agent import LLMConfigModel


def model_config(**fields) -> LLMConfigModel:
    """Model config."""
    return LLMConfigModel(**fields)


class TestApiKey:
    """Test cases for credentials coming from the model block."""

    def test_the_model_block_api_key_is_used(self):
        """Test the model block api key is used."""
        llm = LLMFactory.create_llm(
            model_config(provider='openai', name='gpt-4o-mini', api_key='sk-block')
        )

        assert llm.api_key == 'sk-block'

    def test_a_kwarg_overrides_the_model_block(self):
        """Test a kwarg overrides the model block."""
        llm = LLMFactory.create_llm(
            model_config(provider='openai', name='gpt-4o-mini', api_key='sk-block'),
            api_key='sk-kwarg',
        )

        assert llm.api_key == 'sk-kwarg'

    def test_the_environment_is_the_fallback(self, monkeypatch):
        """Nothing configured, so the SDK's own env lookup still applies."""
        monkeypatch.setenv('OPENAI_API_KEY', 'sk-env')

        llm = LLMFactory.create_llm(model_config(provider='openai', name='gpt-4o-mini'))

        assert llm.client.api_key == 'sk-env'

    def test_anthropic_takes_one_too(self):
        """Test anthropic takes one too."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='anthropic',
                name='claude-3-5-sonnet-20240620',
                api_key='sk-block',
            )
        )

        assert llm.api_key == 'sk-block'


class TestOllamaBaseUrl:
    """Test cases for an ollama block with no base_url."""

    def test_the_documented_default_applies(self):
        """This raised AttributeError on None.rstrip('/') at build time."""
        llm = LLMFactory.create_llm(model_config(provider='ollama', name='llama2'))

        assert llm.base_url == 'http://localhost:11434'

    def test_a_configured_base_url_is_used(self):
        """Test a configured base url is used."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='ollama', name='llama2', base_url='http://ollama:11434'
            )
        )

        assert llm.base_url == 'http://ollama:11434'


class TestModelBlockTemperature:
    """Every provider's wrapper takes it from one place, or none of them do.

    Read per-provider, `model.temperature` was honoured by azure_openai and
    openai_vllm and silently dropped by the rest. Agents built from YAML were
    unaffected - both builders re-apply it after construction - but a caller of
    the factory got the wrapper's default 0.7 with nothing to say the value had
    been dropped.
    """

    PROVIDERS = [
        ('openai', {'name': 'gpt-4o-mini', 'api_key': 'sk-test'}),
        ('anthropic', {'name': 'claude-3-5-sonnet-20240620', 'api_key': 'sk-test'}),
        ('gemini', {'name': 'gemini-2.5-flash', 'api_key': 'sk-test'}),
        ('ollama', {'name': 'llama2'}),
        (
            'openai_vllm',
            {'name': 'mistral', 'base_url': 'http://localhost:8000/v1', 'api_key': 'k'},
        ),
        (
            'azure_openai',
            {
                'name': 'gpt-4.1-mini',
                'api_key': 'sk-test',
                'azure_endpoint': 'https://example.cognitiveservices.azure.com',
            },
        ),
        (
            'vertexai',
            {
                'name': 'gemini-2.5-flash',
                'project': 'test-project',
                'base_url': 'https://example.invalid',
            },
        ),
    ]

    @pytest.mark.parametrize('provider,fields', PROVIDERS)
    def test_it_reaches_every_provider(self, provider, fields):
        """Test it reaches every provider."""
        llm = LLMFactory.create_llm(
            model_config(provider=provider, temperature=0.3, **fields)
        )

        assert llm.temperature == 0.3

    def test_zero_is_not_read_as_unset(self):
        """0.0 is falsy, and the most deliberate temperature there is."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='openai', name='gpt-4o-mini', api_key='sk-test', temperature=0
            )
        )

        assert llm.temperature == 0

    def test_unset_falls_through_to_the_wrapper_default(self):
        """Test unset falls through to the wrapper default."""
        llm = LLMFactory.create_llm(
            model_config(provider='openai', name='gpt-4o-mini', api_key='sk-test')
        )

        assert llm.temperature == 0.7

    def test_a_kwarg_overrides_the_model_block(self):
        """Test a kwarg overrides the model block."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='openai',
                name='gpt-4o-mini',
                api_key='sk-test',
                temperature=0.3,
            ),
            temperature=0.9,
        )

        assert llm.temperature == 0.9


class TestModelBlockGenerationParams:
    """`model.max_tokens` and `model.timeout` were dead fields."""

    def test_max_tokens_is_named_for_the_provider(self):
        """Test max tokens is named for the provider."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='openai',
                name='gpt-4o-mini',
                api_key='sk-test',
                max_tokens=500,
            )
        )

        assert llm.kwargs == {'max_completion_tokens': 500}

    def test_max_tokens_for_ollama(self):
        """Test max tokens for ollama."""
        llm = LLMFactory.create_llm(
            model_config(provider='ollama', name='llama2', max_tokens=500)
        )

        assert llm.kwargs == {'num_predict': 500}

    def test_timeout_configures_the_client(self):
        """A request timeout is a client option, not a generation param."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='openai', name='gpt-4o-mini', api_key='sk-test', timeout=30
            )
        )

        assert llm.client.timeout == 30
        assert llm.kwargs == {}

    def test_timeout_is_skipped_where_it_would_be_meaningless(self):
        """Ollama would otherwise carry it into `options` as a sampling param."""
        llm = LLMFactory.create_llm(
            model_config(provider='ollama', name='llama2', timeout=30)
        )

        assert llm.kwargs == {}

    def test_nothing_configured_leaves_kwargs_empty(self):
        """Test nothing configured leaves kwargs empty."""
        llm = LLMFactory.create_llm(
            model_config(provider='openai', name='gpt-4o-mini', api_key='sk-test')
        )

        assert llm.kwargs == {}


class TestProviderAliases:
    """LLMConfigModel accepts these; the factory used to reject them."""

    def test_claude_builds_an_anthropic_llm(self):
        """Test claude builds an anthropic llm."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='claude',
                name='claude-3-5-sonnet-20240620',
                api_key='sk-test',
            )
        )

        assert llm.provider_name == 'anthropic'

    def test_google_builds_a_gemini_llm(self):
        """Test google builds a gemini llm."""
        llm = LLMFactory.create_llm(
            model_config(provider='google', name='gemini-2.5-flash', api_key='sk-test')
        )

        assert llm.provider_name == 'gemini'

    def test_an_unknown_provider_still_raises(self):
        """Test an unknown provider still raises."""
        config = LLMConfigModel.model_construct(
            provider='something-new', name='gpt-4o-mini'
        )

        with pytest.raises(ValueError, match='Unsupported model provider'):
            LLMFactory.create_llm(config)


class TestRootFloModelBlock:
    """The proxy resolves its own configuration, so it gets what is set here."""

    def test_temperature_is_left_unset_when_the_block_omits_it(self):
        """Unset means the fetched configuration's own value applies."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='rootflo',
                model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
                base_url='https://example.invalid',
            )
        )

        assert llm._temperature_explicit is False

    def test_a_block_temperature_is_passed_through(self):
        """Test a block temperature is passed through."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='rootflo',
                model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
                base_url='https://example.invalid',
                temperature=0.3,
            )
        )

        assert llm.temperature == 0.3
        assert llm._temperature_explicit is True

    def test_max_tokens_is_deferred_for_later_translation(self):
        """The provider is unknown until the fetch, so the name is canonical."""
        llm = LLMFactory.create_llm(
            model_config(
                provider='rootflo',
                model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
                base_url='https://example.invalid',
                max_tokens=500,
            )
        )

        assert llm._kwargs == {'max_tokens': 500}


if __name__ == '__main__':
    pytest.main([__file__])
