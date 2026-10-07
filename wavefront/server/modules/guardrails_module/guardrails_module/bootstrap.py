"""Construct GuardrailsContainer only when [guardrails] enabled is true.

Keeps the DI container (and the engine it builds) out of the process when the
feature is off. spaCy/Presidio still only load when the engine is built/warmed.
"""

from typing import Any, Mapping, Optional

from common_module.log.logger import logger
from guardrails_module.services.engine_factory import cfg_bool


def create_guardrails_container_if_enabled(
    config: Mapping[str, Any],
    *,
    db_client: Any,
    cache_manager: Any,
) -> Optional[Any]:
    """Return a wired GuardrailsContainer, or None when guardrails are disabled."""
    if not cfg_bool(config.get('guardrails') or {}, 'enabled', False):
        logger.info(
            'Guardrails disabled ([guardrails] enabled=false); '
            'skipping container construction'
        )
        return None

    from guardrails_module.container import GuardrailsContainer

    container = GuardrailsContainer(
        db_client=db_client,
        cache_manager=cache_manager,
    )
    container.config.from_dict(config)
    return container
