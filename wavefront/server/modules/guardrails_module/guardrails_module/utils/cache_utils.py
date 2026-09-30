"""Cache key generation for guardrail policies."""


def get_guardrail_policy_cache_key(namespace: str) -> str:
    """Cache key for a namespace's guardrail policy."""
    return f'guardrail_policy:{namespace}'
