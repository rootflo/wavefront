"""Error-reporting (Sentry) settings built from an app's config.ini."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Mapping

from common_module.log.logger import logger

_BREADCRUMB_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
}


def _text(value: Any) -> str | None:
    """A config value as a stripped string; empty or missing becomes None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sample_rate(value: Any) -> float:
    text = _text(value)
    if text is None:
        return 1.0
    try:
        rate = float(text)
    except ValueError:
        rate = math.nan
    if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
        logger.warning(
            f'[sentry] sample_rate must be a number from 0 to 1, got {text!r}; using 1.0'
        )
        return 1.0
    return rate


def _breadcrumb_level(value: Any) -> int:
    text = _text(value)
    if text is None:
        return logging.WARNING
    level = _BREADCRUMB_LEVELS.get(text.upper())
    if level is None:
        logger.warning(
            f'[sentry] breadcrumb_level must be one of {", ".join(_BREADCRUMB_LEVELS)}, '
            f'got {text!r}; using WARNING'
        )
        return logging.WARNING
    return level


@dataclass(frozen=True)
class ErrorReportingSettings:
    service_name: str
    # Empty or missing disables error reporting: Sentry is never initialised.
    dsn: str | None = None
    environment: str = 'dev'
    release: str | None = None
    sample_rate: float = 1.0
    # INFO logs carry secrets and personal data in places, so breadcrumbs
    # start at WARNING until those logs are cleaned up.
    breadcrumb_level: int = logging.WARNING

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        default_service_name: str,
    ) -> ErrorReportingSettings:
        """Build from the ``[sentry]`` section. Never raises on bad values."""
        env = config.get('env_config') or {}
        sentry = config.get('sentry') or {}
        return cls(
            service_name=_text(sentry.get('service_name')) or default_service_name,
            dsn=_text(sentry.get('dsn')),
            environment=_text(sentry.get('environment'))
            or _text(env.get('app_env'))
            or 'dev',
            release=_text(sentry.get('release')),
            sample_rate=_sample_rate(sentry.get('sample_rate')),
            breadcrumb_level=_breadcrumb_level(sentry.get('breadcrumb_level')),
        )
