"""Canonical generation-parameter names, and the wire name each provider uses.

A token limit is `max_tokens` to Anthropic and vLLM, `max_completion_tokens` to
OpenAI/Azure/Groq, `max_output_tokens` to Gemini and `num_predict` to Ollama.
Callers write one canonical name - in a YAML `settings:` block or an LLM
inference config - so the translation has to live in one shared place.

Two failures come from not having one. A stored config that was created for one
provider and later pointed at another keeps the first provider's key, so the
request carries two token limits at once and OpenAI rejects the pair outright
(`'max_tokens' and 'max_completion_tokens' at the same time is not supported`).
And a config written with `max_tokens` against a provider that calls it
something else is silently ignored.
"""

from typing import Any, Dict, Mapping, Optional

# The name callers write. Every provider-specific spelling maps back to this.
CANONICAL_TOKEN_LIMIT = 'max_tokens'

# Every spelling a token limit can arrive under, whatever the provider.
TOKEN_LIMIT_ALIASES = (
    'max_completion_tokens',
    'max_tokens',
    'max_output_tokens',
    'num_predict',
)

# Generation params that are canonically named, i.e. the same for every
# provider that supports them at all. Used to validate a YAML `settings:` block.
CANONICAL_GENERATION_PARAMS = (
    CANONICAL_TOKEN_LIMIT,
    'top_p',
    'top_k',
    'frequency_penalty',
    'presence_penalty',
    'seed',
)

# Provider spellings seen across an inference config's `type`, a YAML
# `model.provider`, and the rootflo proxy's own type strings.
_PROVIDER_ALIASES = {
    'claude': 'anthropic',
    'google': 'gemini',
    'openai_vllm': 'vllm',
    'azureopenai': 'azure_openai',
}

_PROVIDER_TOKEN_LIMIT = {
    'openai': 'max_completion_tokens',
    'azure_openai': 'max_completion_tokens',
    'groq': 'max_completion_tokens',
    'anthropic': 'max_tokens',
    'vllm': 'max_tokens',
    'gemini': 'max_output_tokens',
    'ollama': 'num_predict',
}


def canonical_provider(provider: Optional[str]) -> str:
    """Resolve a provider spelling to the one used as a key here.

    Args:
        provider: Provider name from a config `type`, YAML `model.provider`,
            or an LLM wrapper's `provider_name`

    Returns:
        The canonical provider name, or '' when there is nothing to resolve
    """
    if not provider:
        return ''
    name = provider.strip().lower()
    return _PROVIDER_ALIASES.get(name, name)


def token_limit_key(provider: Optional[str]) -> str:
    """The name `provider` accepts a token limit under.

    Args:
        provider: Provider name or alias

    Returns:
        The provider's token-limit key; `max_tokens` for an unknown provider,
        which is the most widely accepted spelling
    """
    return _PROVIDER_TOKEN_LIMIT.get(
        canonical_provider(provider), CANONICAL_TOKEN_LIMIT
    )


def normalize_generation_params(
    params: Optional[Mapping[str, Any]], provider: Optional[str]
) -> Dict[str, Any]:
    """Drop nulls and collapse token-limit aliases onto the one `provider` takes.

    A null is dropped rather than forwarded so a blank config field falls
    through to the provider's own default instead of overriding it with None.

    When several token-limit aliases are present, the provider's own key wins;
    a value stored under another provider's key is carried over rather than
    dropped, since it is what the user last asked for.

    Args:
        params: Generation params under any mix of token-limit spellings
        provider: Provider name or alias the params are destined for

    Returns:
        A new dict carrying at most one token limit, named for `provider`
    """
    if not params:
        return {}

    preferred = token_limit_key(provider)

    token_limit = None
    for alias in (preferred, *TOKEN_LIMIT_ALIASES):
        value = params.get(alias)
        if value is not None:
            token_limit = value
            break

    normalized = {
        key: value
        for key, value in params.items()
        if value is not None and key not in TOKEN_LIMIT_ALIASES
    }
    if token_limit is not None:
        normalized[preferred] = token_limit

    return normalized


def merge_generation_params(
    base: Optional[Mapping[str, Any]],
    overrides: Optional[Mapping[str, Any]],
    provider: Optional[str],
) -> Dict[str, Any]:
    """Merge `overrides` over `base`, keeping exactly one token limit.

    Each side is normalized before merging, which is what makes the precedence
    hold across spellings: an override written as `max_tokens` replaces a base
    value stored as `max_completion_tokens` instead of travelling alongside it
    and having the provider reject the pair.

    Args:
        base: The less specific params, e.g. an LLM inference config's
        overrides: The more specific params, e.g. a YAML `settings:` block's
        provider: Provider name or alias the result is destined for

    Returns:
        A new dict carrying at most one token limit, named for `provider`
    """
    return {
        **normalize_generation_params(base, provider),
        **normalize_generation_params(overrides, provider),
    }
