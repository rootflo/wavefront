"""
Tests for RootFloLLM applying the generation parameters of the configuration it
fetches.

The proxy fetches its configuration by model_id and used to keep only the model
name and provider type from the response, so everything the configuration set -
temperature, top_p, max_tokens - was dropped and the request went out with the
provider's defaults.
"""

from unittest.mock import AsyncMock, patch

import pytest

from flo_ai.llm.rootflo_llm import RootFloLLM

BASE_URL = 'https://example.invalid'
MODEL_ID = '68baf67b-ff67-4bb1-a663-bcf08227d012'


def build_llm(**kwargs) -> RootFloLLM:
    return RootFloLLM(base_url=BASE_URL, model_id=MODEL_ID, **kwargs)


def stub_fetch(llm: RootFloLLM, parameters: dict, llm_type: str = 'openai') -> None:
    """Stand in for the HTTP call, returning a configuration of the given type."""
    llm._fetch_llm_config_async = AsyncMock(
        return_value={
            'llm_model': 'gpt-4.1-mini',
            'type': llm_type,
            'parameters': parameters,
        }
    )


class TestConfigParametersReachTheWrapper:
    """Whatever the configuration sets should reach the underlying SDK."""

    async def test_generation_parameters_are_forwarded(self):
        llm = build_llm()
        stub_fetch(llm, {'top_p': 0.5, 'max_completion_tokens': 500})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'top_p': 0.5, 'max_completion_tokens': 500}

    async def test_null_parameters_are_dropped(self):
        """A null must not override the provider's own default."""
        llm = build_llm()
        stub_fetch(llm, {'top_p': 0.5, 'seed': None})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'top_p': 0.5}

    async def test_reserved_keys_cannot_collide(self):
        """These are passed explicitly, so forwarding them would be a duplicate."""
        llm = build_llm()
        stub_fetch(llm, {'model': 'wrong', 'api_key': 'wrong', 'top_p': 0.5})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'top_p': 0.5}
        assert llm._llm.model == 'gpt-4.1-mini'

    async def test_caller_kwargs_win_over_the_configuration(self):
        llm = build_llm(top_p=0.9)
        stub_fetch(llm, {'top_p': 0.5})

        await llm._ensure_initialized()

        assert llm._llm.kwargs['top_p'] == 0.9

    async def test_missing_parameters_are_tolerated(self):
        llm = build_llm()
        stub_fetch(llm, {})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {}

    async def test_api_version_is_reserved(self):
        """Azure is proxied as a plain OpenAI client, whose create() has no such
        parameter, so forwarding it would fail the request."""
        llm = build_llm()
        stub_fetch(llm, {'api_version': '2024-10-21', 'top_p': 0.5}, 'azure_openai')

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'top_p': 0.5}


class TestTokenLimitIsNamedForTheProvider:
    """The proxy only learns the provider from the configuration it fetches."""

    async def test_the_canonical_name_is_translated(self):
        llm = build_llm()
        stub_fetch(llm, {'max_tokens': 500})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'max_completion_tokens': 500}

    async def test_the_rejected_pair_collapses(self):
        """Both in one request is a hard failure from the OpenAI family."""
        llm = build_llm()
        stub_fetch(llm, {'max_tokens': 500, 'max_completion_tokens': 800})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'max_completion_tokens': 800}

    async def test_anthropic_keeps_its_own_spelling(self):
        llm = build_llm()
        stub_fetch(llm, {'max_tokens': 500}, 'anthropic')

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'max_tokens': 500}

    @patch('flo_ai.llm.gemini_llm.genai.Client')
    async def test_gemini_renames_it(self, _client):
        """The client is patched: a real one is async, and nothing here calls it."""
        llm = build_llm()
        stub_fetch(llm, {'max_tokens': 500}, 'gemini')

        await llm._ensure_initialized()

        assert llm._llm._generation_config_kwargs({}) == {'max_output_tokens': 500}

    async def test_a_caller_param_is_translated_too(self):
        """This is the path a YAML settings.max_tokens takes."""
        llm = build_llm()
        llm.apply_generation_params({'max_tokens': 500})
        stub_fetch(llm, {})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'max_completion_tokens': 500}

    async def test_a_caller_param_outranks_the_configuration(self):
        llm = build_llm()
        llm.apply_generation_params({'max_tokens': 100})
        stub_fetch(llm, {'max_completion_tokens': 800})

        await llm._ensure_initialized()

        assert llm._llm.kwargs == {'max_completion_tokens': 100}


class TestTemperaturePrecedence:
    """Caller -> configuration -> default."""

    async def test_configured_temperature_applies_when_caller_is_silent(self):
        llm = build_llm()
        stub_fetch(llm, {'temperature': 0.0})

        await llm._ensure_initialized()

        assert llm.temperature == 0.0
        assert llm._llm.temperature == 0.0

    async def test_constructor_temperature_beats_the_configuration(self):
        llm = build_llm(temperature=0.9)
        stub_fetch(llm, {'temperature': 0.0})

        await llm._ensure_initialized()

        assert llm._llm.temperature == 0.9

    async def test_assigned_temperature_beats_the_configuration(self):
        """This is the path a YAML settings.temperature takes."""
        llm = build_llm()
        llm.temperature = 0.2
        stub_fetch(llm, {'temperature': 0.0})

        await llm._ensure_initialized()

        assert llm._llm.temperature == 0.2

    async def test_default_applies_when_nobody_specifies_one(self):
        llm = build_llm()
        stub_fetch(llm, {'top_p': 0.5})

        await llm._ensure_initialized()

        assert llm._llm.temperature == 0.7

    async def test_temperature_zero_survives(self):
        """0.0 is falsy, so it must not be mistaken for 'unset'."""
        llm = build_llm()
        stub_fetch(llm, {'temperature': 0.0})

        await llm._ensure_initialized()

        assert llm._llm.temperature == 0.0


if __name__ == '__main__':
    pytest.main([__file__])
