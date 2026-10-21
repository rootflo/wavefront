"""Settings for the publishing Celery app, from the [celery] section of config.ini."""

from dataclasses import dataclass, fields
from typing import Any, Callable

from common_module.log.logger import logger

DEFAULT_MAX_QUEUE_DEPTH = 10000
DEFAULT_QUEUE_DEPTH_CACHE_TTL_SECONDS = 1.0
DEFAULT_QUEUE_DEPTH_WARN_RATIO = 0.8
DEFAULT_BACKPRESSURE_RETRY_AFTER_SECONDS = 30
DEFAULT_BROKER_SOCKET_TIMEOUT_SECONDS = 2.0


def _coerce(name: str, raw: Any, cast: Callable[[Any], Any], default: Any) -> Any:
    if raw is None or (isinstance(raw, str) and raw.strip() == ''):
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logger.warning(f'Celery: {name}={raw!r} is not usable, using {default}')
        return default


@dataclass(frozen=True)
class CeleryProducerSettings:
    """Values arrive as ini strings, or None for an undefined key; both are
    coerced, and unusable ones fall back to the default."""

    # Ready tasks at which new work gets a 429. <= 0 disables the gate.
    max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH
    # How long a measured depth is reused before re-probing.
    queue_depth_cache_ttl_seconds: float = DEFAULT_QUEUE_DEPTH_CACHE_TTL_SECONDS
    # Fraction of the limit above which the depth is logged as a warning.
    queue_depth_warn_ratio: float = DEFAULT_QUEUE_DEPTH_WARN_RATIO
    backpressure_retry_after_seconds: int = DEFAULT_BACKPRESSURE_RETRY_AFTER_SECONDS
    # Producer only; the worker's consuming app needs long blocking reads.
    broker_socket_timeout_seconds: float = DEFAULT_BROKER_SOCKET_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        casts: dict[str, Callable[[Any], Any]] = {
            'max_queue_depth': int,
            'queue_depth_cache_ttl_seconds': float,
            'queue_depth_warn_ratio': float,
            'backpressure_retry_after_seconds': int,
            'broker_socket_timeout_seconds': float,
        }
        for field in fields(self):
            value = _coerce(
                f'[celery] {field.name}',
                getattr(self, field.name),
                casts[field.name],
                field.default,
            )
            object.__setattr__(self, field.name, value)
