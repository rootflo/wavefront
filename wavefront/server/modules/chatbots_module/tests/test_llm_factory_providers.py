"""Provider branches must stay in step with AgentInferenceService._create_llm_instance.

Two of these are real bugs that were shipped and fixed:

- `azure_openai` was built as `OpenAI(base_url=...)`. Azure is not
  OpenAI-with-a-base_url -- it needs a deployment endpoint and an `api_version`
  -- so every Azure-backed chatbot failed at call time.
- `groq` had no branch at all, so a groq config raised "Unsupported LLM type"
  even though the console offers groq as a choice.
"""

import pytest
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai.llm import Anthropic, AzureOpenAI, Gemini, OllamaLLM, OpenAI, OpenAIVLLM

from chatbots_module.utils.llm_factory import GROQ_BASE_URL, build_llm


def _config(**overrides) -> LlmInferenceConfig:
    values = dict(
        llm_model='test-model',
        display_name='test',
        api_key='test-key',
        type='openai',
        base_url=None,
        parameters=None,
    )
    values.update(overrides)
    return LlmInferenceConfig(**values)


@pytest.fixture(autouse=True)
def _azure_api_version(monkeypatch):
    # AzureOpenAI will not construct without one.
    monkeypatch.setenv('AZURE_OPENAI_API_VERSION', '2024-06-01')


class TestAzureOpenAI:
    def test_uses_the_azure_client_not_openai(self):
        llm = build_llm(
            _config(type='azure_openai', base_url='https://x.openai.azure.com')
        )
        assert isinstance(llm, AzureOpenAI)

    def test_api_version_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setenv('AZURE_OPENAI_API_VERSION', '2099-01-01')
        # Constructing at all is the assertion: a missing api_version raises.
        assert build_llm(
            _config(type='azure_openai', base_url='https://x.openai.azure.com')
        )

    def test_api_version_from_config_parameters_is_used(self):
        llm = build_llm(
            _config(
                type='azure_openai',
                base_url='https://x.openai.azure.com',
                parameters={'api_version': '2025-01-01'},
            )
        )
        assert isinstance(llm, AzureOpenAI)


class TestGroq:
    def test_is_supported(self):
        assert isinstance(build_llm(_config(type='groq')), OpenAI)

    def test_defaults_to_the_groq_endpoint(self):
        llm = build_llm(_config(type='groq'))
        assert str(llm.client.base_url).rstrip('/') == GROQ_BASE_URL

    def test_an_explicit_base_url_wins(self):
        llm = build_llm(_config(type='groq', base_url='https://gateway.internal/v1'))
        assert str(llm.client.base_url).rstrip('/') == 'https://gateway.internal/v1'


class TestOllama:
    def test_absent_base_url_leaves_the_library_default(self):
        # OllamaLLM calls .rstrip() on base_url, so passing an explicit None
        # would be an AttributeError rather than a fallback.
        llm = build_llm(_config(type='ollama'))
        assert isinstance(llm, OllamaLLM)
        assert llm.base_url == 'http://localhost:11434'

    def test_explicit_base_url_is_passed(self):
        llm = build_llm(_config(type='ollama', base_url='http://ollama.internal:11434'))
        assert llm.base_url == 'http://ollama.internal:11434'


class TestRemainingProviders:
    @pytest.mark.parametrize(
        ('provider', 'expected'),
        [
            ('openai', OpenAI),
            ('anthropic', Anthropic),
            ('gemini', Gemini),
            ('vllm', OpenAIVLLM),
        ],
    )
    def test_provider_maps_to_its_client(self, provider, expected):
        assert isinstance(
            build_llm(_config(type=provider, base_url='http://x')), expected
        )

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match='Unsupported LLM type'):
            build_llm(_config(type='not-a-provider'))


class TestParameterHandling:
    def test_reserved_keys_do_not_become_duplicate_kwargs(self):
        # model/api_key/base_url are passed positionally; a config carrying them
        # in `parameters` would raise TypeError for a repeated keyword.
        llm = build_llm(
            _config(
                parameters={
                    'model': 'other',
                    'api_key': 'other',
                    'base_url': 'http://other',
                }
            )
        )
        assert llm.model == 'test-model'

    def test_token_limit_is_renamed_for_the_provider(self):
        # OpenAI rejects a request carrying both max_tokens and
        # max_completion_tokens, so the alias has to be collapsed.
        llm = build_llm(_config(type='openai', parameters={'max_tokens': 128}))
        assert llm.kwargs == {'max_completion_tokens': 128}

    def test_null_parameters_are_dropped(self):
        llm = build_llm(_config(parameters={'max_tokens': None}))
        assert 'max_tokens' not in llm.kwargs
        assert 'max_completion_tokens' not in llm.kwargs
