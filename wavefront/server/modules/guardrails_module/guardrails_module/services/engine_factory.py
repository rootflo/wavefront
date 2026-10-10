"""Constructs the guardrails engine, its safety providers and its caches."""

from typing import Any, List, Optional

from common_module.log.logger import logger

from guardrails_module.services.verdict_cache import (
    DEFAULT_TTL_SECONDS,
    RedisVerdictCache,
)

_TRUTHY = {'1', 'true', 'yes', 'on'}
_FALSY = {'0', 'false', 'no', 'off'}


def _optional_int(raw: Any, default: int) -> int:
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(f'Guardrails: {raw!r} is not an integer, using {default}')
        return default


def cfg_bool(raw: Any, default: bool) -> bool:
    """Parse a config.ini-style boolean; empty/missing uses ``default``."""
    if raw is None or str(raw).strip() == '':
        return default
    value = str(raw).strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning(f'Guardrails: {raw!r} is not a boolean, using {default}')
    return default


def build_guardrails_engine(
    policy_resolver: Any,
    audit_sink: Any = None,
    cache_manager: Any = None,
    *,
    azure_content_safety_endpoint: str | None = None,
    azure_content_safety_key: str | None = None,
    verdict_cache_chars: str | int | None = None,
    verdict_cache_secret: str | None = None,
    verdict_cache_shared: str | bool | None = None,
    verdict_cache_ttl: str | int | None = None,
    guardrails_enabled: str | bool | None = None,
    spacy_model_url: str | None = None,
    model_cache_dir: str | None = None,
):
    """Build a process-wide engine with whatever providers are available."""
    import os
    from flo_ai.guardrails import VERDICT_CACHE_CHAR_BUDGET, GuardrailsEngine

    adapters: List[Any] = []

    is_enabled = cfg_bool(
        guardrails_enabled
        if guardrails_enabled is not None
        else os.getenv('GUARDRAILS_ENABLED'),
        False,
    )

    if not is_enabled:
        logger.info(
            'Guardrails: Subsystem disabled (GUARDRAILS_ENABLED=false); no adapters registered'
        )
    else:
        effective_url = (
            spacy_model_url or os.getenv('GUARDRAILS_SPACY_MODEL_URL') or ''
        ).strip() or None
        effective_cache_dir = (
            model_cache_dir or os.getenv('GUARDRAILS_MODEL_CACHE_DIR') or ''
        ).strip() or None

        if effective_url:
            try:
                import presidio_analyzer  # noqa: F401
                import presidio_anonymizer  # noqa: F401

                from flo_ai.guardrails.adapters import PresidioAdapter

                adapters.append(
                    PresidioAdapter(
                        model_url=effective_url,
                        cache_dir=effective_cache_dir,
                    )
                )
                logger.info(
                    f'Guardrails: Presidio PII adapter registered (url={effective_url})'
                )
            except Exception as exc:
                logger.warning(
                    f'Guardrails: Presidio unavailable, PII checks cannot run ({exc}). '
                    'Configure GUARDRAILS_SPACY_MODEL_URL or install with: '
                    "uv pip install 'presidio-analyzer' 'presidio-anonymizer'"
                )
        else:
            logger.info(
                'Guardrails: Presidio PII not configured '
                '(set [guardrails] spacy_model_url or GUARDRAILS_SPACY_MODEL_URL)'
            )

        endpoint = (azure_content_safety_endpoint or '').strip()
        api_key = (azure_content_safety_key or '').strip()
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

    cache_chars = _optional_int(verdict_cache_chars, VERDICT_CACHE_CHAR_BUDGET)
    verdict_cache = _build_verdict_cache(
        cache_manager=cache_manager,
        cache_chars=cache_chars,
        verdict_cache_shared=verdict_cache_shared,
        verdict_cache_secret=verdict_cache_secret,
        verdict_cache_ttl=verdict_cache_ttl,
    )
    cache_secret = (verdict_cache_secret or '').strip() or None

    engine = GuardrailsEngine(
        resolver=policy_resolver,
        adapters=adapters,
        audit_sink=audit_sink,
        verdict_cache_chars=cache_chars,
        verdict_cache=verdict_cache,
        cache_key_secret=cache_secret,
        enabled=is_enabled,
    )
    logger.info(f'Guardrails engine ready with adapters: {engine.registered or "none"}')
    return engine


def _build_verdict_cache(
    cache_manager: Any,
    cache_chars: int,
    verdict_cache_shared: Any,
    verdict_cache_secret: str | None,
    verdict_cache_ttl: Any,
) -> Optional[Any]:
    from flo_ai.guardrails import TieredVerdictCache, build_local_cache

    if cache_manager is None:
        logger.info(
            'Guardrails: no cache manager supplied, verdicts stay per-process '
            f'({cache_chars} char budget)'
        )
        return None

    if not cfg_bool(verdict_cache_shared, True):
        logger.info(
            'Guardrails: shared verdict cache disabled in config, '
            'verdicts stay per-process'
        )
        return None

    cache_secret = (verdict_cache_secret or '').strip()
    if not cache_secret:
        logger.warning(
            'Guardrails: shared verdict cache disabled because '
            'verdict_cache_secret is unset. Verdicts stay per-process.'
        )
        return None

    ttl = _optional_int(verdict_cache_ttl, DEFAULT_TTL_SECONDS)

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
