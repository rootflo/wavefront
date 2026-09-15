"""Constructs the guardrails engine and its safety providers."""

import os
from typing import Any, List

from common_module.log.logger import logger


def build_guardrails_engine(policy_resolver: Any, audit_sink: Any = None):
    """Build a process-wide engine with whatever providers are available.

    Adapters are registered once at startup, not per request: Presidio loads a
    spaCy model on first use and the Azure client owns a connection pool.

    A provider that cannot be constructed is simply not registered. That is not
    a silent downgrade — the engine treats a policy naming an unregistered
    adapter as a misconfiguration and fails closed, so a missing dependency
    surfaces as blocked traffic and an error log rather than as checks that
    quietly stop running.
    """
    from flo_ai.guardrails import GuardrailsEngine

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

    engine = GuardrailsEngine(
        resolver=policy_resolver, adapters=adapters, audit_sink=audit_sink
    )
    logger.info(f'Guardrails engine ready with adapters: {engine.registered or "none"}')
    return engine
