"""
Tests for the canonical generation-param names and their per-provider spellings.

A token limit is `max_tokens` to Anthropic and vLLM, `max_completion_tokens` to
OpenAI/Azure/Groq, `max_output_tokens` to Gemini and `num_predict` to Ollama.
Without one place owning that mapping, a stored config that was created for one
provider and later pointed at another carries two of those keys at once, and
OpenAI rejects the request: `'max_tokens' and 'max_completion_tokens' at the
same time is not supported`.
"""

import pytest

from flo_ai.helpers.generation_params import (
    CANONICAL_GENERATION_PARAMS,
    canonical_provider,
    merge_generation_params,
    normalize_generation_params,
    token_limit_key,
    unsupported_params,
)


class TestTokenLimitKey:
    """Each provider's own name for the token limit."""

    @pytest.mark.parametrize(
        'provider,expected',
        [
            ('openai', 'max_completion_tokens'),
            ('azure_openai', 'max_completion_tokens'),
            ('groq', 'max_completion_tokens'),
            ('anthropic', 'max_tokens'),
            ('vllm', 'max_tokens'),
            ('gemini', 'max_output_tokens'),
            ('ollama', 'num_predict'),
        ],
    )
    def test_known_providers(self, provider, expected):
        """Test known providers."""
        assert token_limit_key(provider) == expected

    @pytest.mark.parametrize(
        'alias,expected',
        [
            ('claude', 'max_tokens'),
            ('google', 'max_output_tokens'),
            ('openai_vllm', 'max_tokens'),
            ('OpenAI', 'max_completion_tokens'),
            (' openai ', 'max_completion_tokens'),
        ],
    )
    def test_aliases_and_casing(self, alias, expected):
        """The same provider is spelled several ways across config and YAML."""
        assert token_limit_key(alias) == expected

    @pytest.mark.parametrize('provider', [None, '', 'rootflo', 'something-new'])
    def test_unknown_provider_keeps_the_widest_spelling(self, provider):
        """`max_tokens` is the one most providers accept, so it is the fallback."""
        assert token_limit_key(provider) == 'max_tokens'


class TestCanonicalProvider:
    """Test cases for resolving provider spellings."""

    def test_aliases_resolve(self):
        """Test aliases resolve."""
        assert canonical_provider('claude') == 'anthropic'
        assert canonical_provider('google') == 'gemini'
        assert canonical_provider('openai_vllm') == 'vllm'

    def test_nothing_to_resolve(self):
        """Test nothing to resolve."""
        assert canonical_provider(None) == ''
        assert canonical_provider('') == ''
        assert canonical_provider('openai') == 'openai'


class TestNormalizeGenerationParams:
    """Test cases for renaming the token limit and dropping nulls."""

    def test_canonical_name_is_translated(self):
        """Test canonical name is translated."""
        assert normalize_generation_params({'max_tokens': 500}, 'openai') == {
            'max_completion_tokens': 500
        }
        assert normalize_generation_params({'max_tokens': 500}, 'gemini') == {
            'max_output_tokens': 500
        }
        assert normalize_generation_params({'max_tokens': 500}, 'ollama') == {
            'num_predict': 500
        }

    def test_the_provider_pair_collapses_to_one_key(self):
        """This pair in one request is a hard 400 from the OpenAI family."""
        normalized = normalize_generation_params(
            {'max_tokens': 500, 'max_completion_tokens': 800}, 'openai'
        )

        assert normalized == {'max_completion_tokens': 800}

    def test_the_providers_own_key_wins_the_collapse(self):
        """The value stored for this provider is the one the user last set."""
        normalized = normalize_generation_params(
            {'max_tokens': 500, 'max_completion_tokens': 800}, 'anthropic'
        )

        assert normalized == {'max_tokens': 500}

    def test_another_providers_value_is_carried_over_not_dropped(self):
        """A config switched to anthropic still meant its token limit to apply."""
        normalized = normalize_generation_params(
            {'max_completion_tokens': 800}, 'anthropic'
        )

        assert normalized == {'max_tokens': 800}

    def test_other_params_pass_through_untouched(self):
        """Only the token limit is spelled differently per provider."""
        params = {'top_p': 0.9, 'seed': 42, 'frequency_penalty': 0.5}

        assert normalize_generation_params(params, 'openai') == params

    def test_nulls_are_dropped(self):
        """A null must fall through to the provider's default, not override it."""
        normalized = normalize_generation_params(
            {'top_p': 0.9, 'seed': None, 'max_tokens': None}, 'openai'
        )

        assert normalized == {'top_p': 0.9}

    def test_zero_survives(self):
        """0 is a value, not an absent one."""
        assert normalize_generation_params({'top_p': 0}, 'openai') == {'top_p': 0}

    def test_empty_input(self):
        """Test empty input."""
        assert normalize_generation_params(None, 'openai') == {}
        assert normalize_generation_params({}, 'openai') == {}

    def test_the_input_is_not_mutated(self):
        """Callers pass a config's stored parameters, which they still own."""
        params = {'max_tokens': 500, 'top_p': 0.9}

        normalize_generation_params(params, 'openai')

        assert params == {'max_tokens': 500, 'top_p': 0.9}

    def test_normalizing_twice_is_stable(self):
        """The rootflo path normalizes again once the real provider is known."""
        once = normalize_generation_params({'max_tokens': 500}, 'rootflo')
        twice = normalize_generation_params(once, 'gemini')

        assert twice == {'max_output_tokens': 500}


class TestUnsupportedParamsAreDropped:
    """`settings:` offers the same names for every provider; not all have them.

    Forwarding one anyway is a 400 from the vendor endpoints, and for Anthropic
    a local TypeError - its messages.create() has no **kwargs to absorb it.
    """

    def test_openai_family_has_no_top_k(self):
        """Test openai family has no top k."""
        for provider in ('openai', 'azure_openai', 'groq'):
            normalized = normalize_generation_params(
                {'top_k': 40, 'top_p': 0.9}, provider
            )

            assert normalized == {'top_p': 0.9}, provider

    def test_anthropic_has_no_penalties_or_seed(self):
        """Test anthropic has no penalties or seed."""
        normalized = normalize_generation_params(
            {
                'top_k': 40,
                'seed': 42,
                'frequency_penalty': 0.5,
                'presence_penalty': 0.25,
            },
            'anthropic',
        )

        assert normalized == {'top_k': 40}

    def test_vllm_keeps_top_k(self):
        """Its SDK is OpenAI's, but a vLLM server does accept it."""
        assert normalize_generation_params({'top_k': 40}, 'vllm') == {'top_k': 40}
        assert normalize_generation_params({'top_k': 40}, 'openai_vllm') == {
            'top_k': 40
        }

    def test_gemini_and_ollama_keep_everything(self):
        """Test gemini and ollama keep everything."""
        params = {'top_k': 40, 'seed': 42, 'frequency_penalty': 0.5}

        assert normalize_generation_params(params, 'gemini') == params
        assert normalize_generation_params(params, 'ollama') == params

    def test_a_non_canonical_key_is_never_dropped(self):
        """It is somebody's own server knob; extra_body exists to carry it."""
        normalized = normalize_generation_params(
            {'guided_regex': r'\d+', 'repetition_penalty': 1.1}, 'openai'
        )

        assert normalized == {'guided_regex': r'\d+', 'repetition_penalty': 1.1}

    def test_an_unknown_provider_loses_nothing(self):
        """Test an unknown provider loses nothing."""
        params = {'top_k': 40, 'seed': 42}

        assert normalize_generation_params(params, 'something-new') == params
        assert normalize_generation_params(params, None) == params

    def test_the_token_limit_is_never_dropped(self):
        """Every provider has one, under some name."""
        assert normalize_generation_params({'max_tokens': 500}, 'anthropic') == {
            'max_tokens': 500
        }

    def test_the_input_is_not_mutated(self):
        """Test the input is not mutated."""
        params = {'top_k': 40, 'top_p': 0.9}

        normalize_generation_params(params, 'openai')

        assert params == {'top_k': 40, 'top_p': 0.9}

    def test_the_gap_table_is_queryable(self):
        """Exposed so a caller can warn before a request rather than after."""
        assert unsupported_params('azure_openai') == {'top_k'}
        assert unsupported_params('claude') == {
            'frequency_penalty',
            'presence_penalty',
            'seed',
        }
        assert unsupported_params('gemini') == frozenset()


class TestMergeGenerationParams:
    """Test cases for precedence holding across the provider spellings."""

    def test_overrides_win(self):
        """Test overrides win."""
        merged = merge_generation_params({'top_p': 0.1}, {'top_p': 0.9}, 'openai')

        assert merged == {'top_p': 0.9}

    def test_both_sides_contribute(self):
        """Test both sides contribute."""
        merged = merge_generation_params({'top_p': 0.1}, {'seed': 42}, 'openai')

        assert merged == {'top_p': 0.1, 'seed': 42}

    def test_a_canonical_override_replaces_a_provider_spelled_base(self):
        """The failure this exists for: the two would otherwise both be sent.

        `settings.max_tokens` has to override a config's stored
        `max_completion_tokens`, not travel alongside it.
        """
        merged = merge_generation_params(
            {'max_completion_tokens': 800}, {'max_tokens': 100}, 'openai'
        )

        assert merged == {'max_completion_tokens': 100}

    def test_a_base_token_limit_survives_without_an_override(self):
        """Test a base token limit survives without an override."""
        merged = merge_generation_params({'max_tokens': 800}, {'top_p': 0.9}, 'openai')

        assert merged == {'max_completion_tokens': 800, 'top_p': 0.9}

    def test_empty_sides(self):
        """Test empty sides."""
        assert merge_generation_params(None, None, 'openai') == {}
        assert merge_generation_params({'top_p': 0.9}, None, 'openai') == {'top_p': 0.9}
        assert merge_generation_params(None, {'top_p': 0.9}, 'openai') == {'top_p': 0.9}

    def test_a_null_override_does_not_erase_the_base(self):
        """An unset YAML field means 'not specified', not 'clear it'."""
        merged = merge_generation_params({'top_p': 0.1}, {'top_p': None}, 'openai')

        assert merged == {'top_p': 0.1}

    def test_neither_side_is_mutated(self):
        """Test neither side is mutated."""
        base = {'max_tokens': 800}
        overrides = {'top_p': 0.9}

        merge_generation_params(base, overrides, 'openai')

        assert base == {'max_tokens': 800}
        assert overrides == {'top_p': 0.9}


class TestCanonicalParamList:
    """The names a YAML `settings:` block accepts."""

    def test_token_limit_is_canonically_named(self):
        """Test token limit is canonically named."""
        assert 'max_tokens' in CANONICAL_GENERATION_PARAMS

    def test_no_provider_specific_spelling_is_offered(self):
        """Callers write one name; the translation is this module's job."""
        provider_specific = {
            'max_completion_tokens',
            'max_output_tokens',
            'num_predict',
        }

        assert provider_specific.isdisjoint(CANONICAL_GENERATION_PARAMS)


if __name__ == '__main__':
    pytest.main([__file__])
