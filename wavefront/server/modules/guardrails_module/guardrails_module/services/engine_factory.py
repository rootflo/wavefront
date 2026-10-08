"""Constructs the guardrails engine, its safety providers and its caches."""

import os
from typing import Any, List, Mapping, Optional

from common_module.log.logger import logger

from guardrails_module.services.verdict_cache import (
    DEFAULT_TTL_SECONDS,
    RedisVerdictCache,
)

_TRUTHY = {'1', 'true', 'yes', 'on'}
_FALSY = {'0', 'false', 'no', 'off'}

DEFAULT_REGEX_TIMEOUT_SECONDS = 2


def _cfg_int(cfg: Mapping[str, Any], key: str, default: int) -> int:
    raw = cfg.get(key)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(f'Guardrails: {key}={raw!r} is not an integer, using {default}')
        return default


def cfg_bool(cfg: Mapping[str, Any], key: str, default: bool) -> bool:
    """Parse a config.ini-style boolean; empty/missing uses ``default``."""
    raw = cfg.get(key)
    if raw is None or str(raw).strip() == '':
        return default
    value = str(raw).strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning(f'Guardrails: {key}={raw!r} is not a boolean, using {default}')
    return default


# Backward-compatible alias for existing tests/callers.
_cfg_bool = cfg_bool


def _apply_presidio_regex_timeout(cfg: Mapping[str, Any]) -> None:
    """Set REGEX_TIMEOUT_SECONDS before Presidio import (read at module load)."""
    timeout = _cfg_int(cfg, 'regex_timeout_seconds', DEFAULT_REGEX_TIMEOUT_SECONDS)
    if timeout < 1:
        logger.warning(
            f'Guardrails: regex_timeout_seconds={timeout} is too low, '
            f'using {DEFAULT_REGEX_TIMEOUT_SECONDS}'
        )
        timeout = DEFAULT_REGEX_TIMEOUT_SECONDS
    os.environ['REGEX_TIMEOUT_SECONDS'] = str(timeout)


def build_guardrails_engine(
    policy_resolver: Any,
    audit_sink: Any = None,
    cache_manager: Any = None,
    guardrails_config: Mapping[str, Any] | None = None,
):
    """Build a process-wide engine with whatever providers are available."""
    from flo_ai.guardrails import VERDICT_CACHE_CHAR_BUDGET, GuardrailsEngine

    cfg = guardrails_config or {}
    adapters: List[Any] = []

    try:
        _apply_presidio_regex_timeout(cfg)
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

    endpoint = (cfg.get('azure_content_safety_endpoint') or '').strip()
    api_key = (cfg.get('azure_content_safety_key') or '').strip()
    if endpoint and api_key:
        try:
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
            '(set [guardrails] azure_content_safety_endpoint and '
            'azure_content_safety_key)'
        )

    cache_chars = _cfg_int(cfg, 'verdict_cache_chars', VERDICT_CACHE_CHAR_BUDGET)
    verdict_cache = _build_verdict_cache(cache_manager, cache_chars, cfg)
    cache_secret = (cfg.get('verdict_cache_secret') or '').strip() or None

    engine = GuardrailsEngine(
        resolver=policy_resolver,
        adapters=adapters,
        audit_sink=audit_sink,
        verdict_cache_chars=cache_chars,
        verdict_cache=verdict_cache,
        cache_key_secret=cache_secret,
    )
    logger.info(f'Guardrails engine ready with adapters: {engine.registered or "none"}')
    return engine


def _build_verdict_cache(
    cache_manager: Any, cache_chars: int, cfg: Mapping[str, Any]
) -> Optional[Any]:
    from flo_ai.guardrails import TieredVerdictCache, build_local_cache

    if cache_manager is None:
        logger.info(
            'Guardrails: no cache manager supplied, verdicts stay per-process '
            f'({cache_chars} char budget)'
        )
        return None

    if not cfg_bool(cfg, 'verdict_cache_shared', True):
        logger.info(
            'Guardrails: shared verdict cache disabled in config, '
            'verdicts stay per-process'
        )
        return None

    cache_secret = (cfg.get('verdict_cache_secret') or '').strip()
    if not cache_secret:
        logger.warning(
            'Guardrails: shared verdict cache disabled because '
            'verdict_cache_secret is unset. Verdicts stay per-process.'
        )
        return None

    ttl = _cfg_int(cfg, 'verdict_cache_ttl', DEFAULT_TTL_SECONDS)

    try:
        shared = RedisVerdictCache(cache_manager, ttl_seconds=ttl)
    except Exception as exc:
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
