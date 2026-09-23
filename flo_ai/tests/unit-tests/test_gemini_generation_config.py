"""
Tests for building Gemini's GenerateContentConfig from params plus arguments.

`temperature` and `system_instruction` are both ordinary
GenerateContentConfig fields, so either can arrive as a generation param as well
as from an argument - and passing one twice is
`GenerateContentConfig() got multiple values for keyword argument ...`.
An earlier fix popped `temperature` before splatting; `system_instruction`, one
line below it, had exactly the same shape and was left.
"""

import pytest

from flo_ai.llm import Gemini


def gemini_llm(**kwargs) -> Gemini:
    """Gemini llm."""
    return Gemini(model='gemini-2.5-flash', api_key='test-key-123', **kwargs)


class TestGenerationConfig:
    """Test cases for the config a request is built with."""

    def test_a_configured_system_instruction_does_not_collide(self):
        """This raised TypeError before the arguments were merged in one dict."""
        llm = gemini_llm(system_instruction='Be brief.')

        config = llm._generation_config('', {})

        assert config.system_instruction == 'Be brief.'

    def test_the_messages_system_prompt_wins(self):
        """It is the agent's actual prompt; a param is configuration."""
        llm = gemini_llm(system_instruction='Be brief.')

        config = llm._generation_config('You are a translator.', {})

        assert config.system_instruction == 'You are a translator.'

    def test_a_per_call_system_instruction_does_not_collide(self):
        """Test a per call system instruction does not collide."""
        llm = gemini_llm()

        config = llm._generation_config('', {'system_instruction': 'Be brief.'})

        assert config.system_instruction == 'Be brief.'

    def test_the_instance_temperature_applies(self):
        """Test the instance temperature applies."""
        llm = gemini_llm(temperature=0.3)

        config = llm._generation_config('sys', {})

        assert config.temperature == 0.3

    def test_a_per_call_temperature_wins(self):
        """Test a per call temperature wins."""
        llm = gemini_llm(temperature=0.3)

        config = llm._generation_config('sys', {'temperature': 0.9})

        assert config.temperature == 0.9

    def test_temperature_zero_is_not_read_as_unset(self):
        """Test temperature zero is not read as unset."""
        llm = gemini_llm(temperature=0.7)

        config = llm._generation_config('sys', {'temperature': 0})

        assert config.temperature == 0

    def test_the_token_limit_is_renamed(self):
        """Gemini calls it max_output_tokens."""
        llm = gemini_llm(max_tokens=500)

        config = llm._generation_config('sys', {})

        assert config.max_output_tokens == 500

    def test_an_unsupported_param_is_skipped_not_raised(self):
        """A param with no field on this config is warned about, not raised."""
        llm = gemini_llm(not_a_gemini_config_field='x', top_p=0.9)

        config = llm._generation_config('sys', {})

        assert config.top_p == 0.9

    def test_no_params_still_builds(self):
        """Test no params still builds."""
        llm = gemini_llm()

        config = llm._generation_config('sys', {})

        assert config.temperature == 0.7
        assert config.system_instruction == 'sys'


class TestClientConstruction:
    """A base_url means a proxy, and the key has to reach the SDK either way."""

    def test_a_base_url_configuration_builds(self, monkeypatch):
        """The key went only into the header, so the SDK refused to construct:
        `Missing key inputs argument!` unless the environment carried one."""
        monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)

        llm = gemini_llm(base_url='https://gateway.invalid')

        http_options = llm.client._api_client._http_options
        assert http_options.base_url == 'https://gateway.invalid'

    def test_the_proxy_gets_an_authorization_header(self):
        """Test the proxy gets an authorization header."""
        llm = gemini_llm(base_url='https://gateway.invalid')

        headers = llm.client._api_client._http_options.headers or {}
        assert headers['Authorization'] == 'Bearer test-key-123'

    def test_custom_headers_are_merged(self):
        """Test custom headers are merged."""
        llm = gemini_llm(
            base_url='https://gateway.invalid',
            custom_headers={'X-Rootflo-Key': 'app-key'},
        )

        headers = llm.client._api_client._http_options.headers or {}
        assert headers['X-Rootflo-Key'] == 'app-key'
        assert headers['Authorization'] == 'Bearer test-key-123'

    def test_without_a_base_url_the_public_endpoint_applies(self):
        """Test without a base url the public endpoint applies."""
        llm = gemini_llm()

        http_options = llm.client._api_client._http_options
        assert 'googleapis.com' in http_options.base_url


if __name__ == '__main__':
    pytest.main([__file__])
