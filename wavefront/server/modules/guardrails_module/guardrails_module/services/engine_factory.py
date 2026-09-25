"""Constructs the guardrails engine, its safety providers and its caches."""

import os
from typing import Any, List, Optional

from common_module.log.logger import logger

from guardrails_module.services.verdict_cache import (
    DEFAULT_TTL_SECONDS,
    RedisVerdictCache,
)

#: Characters of verdict kept in the per-process tier. ``0`` disables it, which
#: for a redaction policy means Presidio re-runs on every message of every
#: history on every tool-loop iteration - the shared tier cannot stand in,
#: because it refuses to store the redacted body. See VERDICT_CACHE_CHAR_BUDGET
#: in flo_ai for how the budget is charged.
ENV_CACHE_CHARS = 'GUARDRAILS_VERDICT_CACHE_CHARS'

#: HMAC key for cache keys. Without it the key is a plain SHA-256 of the
#: payload, which is brute-forceable when the payload is short - a lone phone
#: number or account ID can be recovered from the digest by anyone who can read
#: Redis. Set this wherever the shared tier is enabled.
ENV_CACHE_SECRET = 'GUARDRAILS_VERDICT_CACHE_SECRET'

#: Seconds a shared entry lives.
ENV_CACHE_TTL = 'GUARDRAILS_VERDICT_CACHE_TTL'

#: Set false to keep verdicts per-process, exactly as before Redis was wired in.
ENV_CACHE_SHARED_ENABLED = 'GUARDRAILS_VERDICT_CACHE_SHARED'

_TRUTHY = {'1', 'true', 'yes', 'on'}
_FALSY = {'0', 'false', 'no', 'off'}


def _env_int(name: str, default: int) -> int:
    """An int from the environment, or the default if it is not usable.

    A typo must not take the cache down silently, nor crash a server at
    startup over a tuning knob. Both are logged loudly enough to find.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(f'Guardrails: {name}={raw!r} is not an integer, using {default}')
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning(f'Guardrails: {name}={raw!r} is not a boolean, using {default}')
    return default


def build_guardrails_engine(
    policy_resolver: Any,
    audit_sink: Any = None,
    cache_manager: Any = None,
):
    """Build a process-wide engine with whatever providers are available.

    Adapters are registered once at startup, not per request: Presidio loads a
    spaCy model on first use and the Azure client owns a connection pool.

    A provider that cannot be constructed is simply not registered. That is not
    a silent downgrade — the engine treats a policy naming an unregistered
    adapter as a misconfiguration and fails closed, so a missing dependency
    surfaces as blocked traffic and an error log rather than as checks that
    quietly stop running.

    ``cache_manager`` is optional for the same reason: without it the engine
    still caches verdicts, just per-process.
    """
    from flo_ai.guardrails import VERDICT_CACHE_CHAR_BUDGET, GuardrailsEngine

    adapters: List[Any] = []

    try:
        # Probe the optional dependency explicitly. PresidioAdapter defers its
        # presidio import until first use, so constructing it proves nothing —
        # without this check the adapter registers on a deployment that cannot
        # run it, the UI offers it as available, and every guarded request then
        # fails inside the adapter. Since an adapter error is INFRASTRUCTURE and
        # defaults to fail-open, the result is traffic passing unchecked while
        # the policy reads as enforced.
        import presidio_analyzer  # noqa: F401
        import presidio_anonymizer  # noqa: F401

        from flo_ai.guardrails.adapters import PresidioAdapter

        adapters.append(PresidioAdapter())
        logger.info('Guardrails: Presidio PII adapter registered')
    except Exception as exc:
        logger.warning(
            f'Guardrails: Presidio unavailable, PII checks cannot run ({exc}). '
            "Install with: uv pip install 'presidio-analyzer' 'presidio-anonymizer' "
            'and python -m spacy download en_core_web_lg'
        )

    endpoint = os.getenv('AZURE_CONTENT_SAFETY_ENDPOINT')
    api_key = os.getenv('AZURE_CONTENT_SAFETY_KEY')
    if endpoint and api_key:
        try:
            # Probe the SDK, for the same reason Presidio is probed above: the
            # adapter defers its azure import to first use, so constructing it
            # proves only that credentials are set. Registering without the SDK
            # is the worst outcome available - the adapter fails at evaluate
            # time as INFRASTRUCTURE, which defaults to fail-open, so the UI
            # reports Azure as enforcing while every request sails past it.
            import azure.ai.contentsafety  # noqa: F401

            from flo_ai.guardrails.adapters import AzureContentSafetyAdapter

            adapters.append(
                AzureContentSafetyAdapter(endpoint=endpoint, api_key=api_key)
            )
            logger.info('Guardrails: Azure Content Safety adapter registered')
        except Exception as exc:
            logger.warning(
                f'Guardrails: Azure Content Safety unavailable ({exc}). '
                "Install with: uv pip install 'azure-ai-contentsafety'"
            )
    else:
        logger.info(
            'Guardrails: Azure Content Safety not configured '
            '(set AZURE_CONTENT_SAFETY_ENDPOINT and AZURE_CONTENT_SAFETY_KEY)'
        )

    cache_chars = _env_int(ENV_CACHE_CHARS, VERDICT_CACHE_CHAR_BUDGET)
    verdict_cache = _build_verdict_cache(cache_manager, cache_chars)

    engine = GuardrailsEngine(
        resolver=policy_resolver,
        adapters=adapters,
        audit_sink=audit_sink,
        verdict_cache_chars=cache_chars,
        verdict_cache=verdict_cache,
        cache_key_secret=os.getenv(ENV_CACHE_SECRET),
    )
    logger.info(f'Guardrails engine ready with adapters: {engine.registered or "none"}')
    return engine


def _build_verdict_cache(cache_manager: Any, cache_chars: int) -> Optional[Any]:
    """A local tier, optionally behind a shared one.

    Returns ``None`` when there is no shared tier to add, which leaves the
    engine to build its own local cache from ``cache_chars`` — the behaviour
    this had before Redis was wired in, and what an SDK embedder gets.
    """
    from flo_ai.guardrails import TieredVerdictCache, build_local_cache

    if cache_manager is None:
        logger.info(
            'Guardrails: no cache manager supplied, verdicts stay per-process '
            f'({cache_chars} char budget)'
        )
        return None

    if not _env_bool(ENV_CACHE_SHARED_ENABLED, True):
        logger.info(
            f'Guardrails: shared verdict cache disabled by '
            f'{ENV_CACHE_SHARED_ENABLED}, verdicts stay per-process'
        )
        return None

    ttl = _env_int(ENV_CACHE_TTL, DEFAULT_TTL_SECONDS)

    try:
        shared = RedisVerdictCache(cache_manager, ttl_seconds=ttl)
    except Exception as exc:
        # Same rule as everywhere else on this path: a cache that cannot be
        # built is a cache you do without, not a server that will not start.
        logger.warning(
            f'Guardrails: shared verdict cache unavailable ({exc}), '
            f'verdicts stay per-process'
        )
        return None

    logger.info(
        f'Guardrails: verdict cache is per-process ({cache_chars} chars) in '
        f'front of Redis (ttl={ttl}s). Redacted content is never shared; '
        f'only content-free verdicts are.'
    )
    return TieredVerdictCache(build_local_cache(cache_chars), shared)
