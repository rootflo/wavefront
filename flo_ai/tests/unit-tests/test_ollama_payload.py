"""
Tests for where Ollama generation params land in the /api/generate payload.

Ollama reads generation params only from `options`, and calls the token limit
`num_predict`. Spreading the wrapper's kwargs at the payload root therefore sent
every configured param - temperature included - into a dead end: accepted by the
server, applied to nothing.
"""

import pytest

from flo_ai.llm import OllamaLLM


def ollama_llm(**kwargs) -> OllamaLLM:
    """Ollama llm."""
    return OllamaLLM(model='llama2', **kwargs)


class TestRequestPayload:
    """Test cases for the payload shape."""

    def test_temperature_is_nested_under_options(self):
        """Test temperature is nested under options."""
        payload = ollama_llm(temperature=0.3)._request_payload('hi')

        assert payload['options'] == {'temperature': 0.3}
        assert 'temperature' not in payload

    def test_generation_params_are_nested_under_options(self):
        """Test generation params are nested under options."""
        payload = ollama_llm(temperature=0.3, top_p=0.9, top_k=40)._request_payload(
            'hi'
        )

        assert payload['options'] == {'temperature': 0.3, 'top_p': 0.9, 'top_k': 40}

    def test_the_token_limit_is_renamed(self):
        """Ollama calls it num_predict; `max_tokens` means nothing to it."""
        payload = ollama_llm(temperature=0.7, max_tokens=500)._request_payload('hi')

        assert payload['options']['num_predict'] == 500
        assert 'max_tokens' not in payload['options']

    def test_a_foreign_token_limit_is_translated_too(self):
        """A config created for OpenAI and pointed at Ollama still means it."""
        payload = ollama_llm(max_completion_tokens=500)._request_payload('hi')

        assert payload['options']['num_predict'] == 500

    def test_request_level_keys_stay_at_the_root(self):
        """`format` is a request field, not a sampling option."""
        payload = ollama_llm(format='json')._request_payload('hi')

        assert payload['format'] == 'json'
        assert 'format' not in payload['options']

    def test_a_caller_options_dict_is_merged_and_wins(self):
        """Test a caller options dict is merged and wins."""
        payload = ollama_llm(
            temperature=0.3, options={'temperature': 0.9, 'num_ctx': 4096}
        )._request_payload('hi')

        assert payload['options'] == {'temperature': 0.9, 'num_ctx': 4096}

    def test_model_and_prompt_are_always_set(self):
        """Test model and prompt are always set."""
        payload = ollama_llm()._request_payload('hi')

        assert payload['model'] == 'llama2'
        assert payload['prompt'] == 'hi'

    def test_overrides_are_applied_at_the_root(self):
        """Test overrides are applied at the root."""
        payload = ollama_llm()._request_payload('hi', stream=False)

        assert payload['stream'] is False


class TestBaseUrl:
    """Test cases for the endpoint the wrapper posts to."""

    def test_the_default_applies_when_omitted(self):
        """Test the default applies when omitted."""
        assert ollama_llm().base_url == 'http://localhost:11434'

    def test_a_trailing_slash_is_trimmed(self):
        """Test a trailing slash is trimmed."""
        assert ollama_llm(base_url='http://ollama:11434/').base_url == (
            'http://ollama:11434'
        )


if __name__ == '__main__':
    pytest.main([__file__])
