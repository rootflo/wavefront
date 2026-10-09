"""Process-wide guardrails startup (before Presidio is imported anywhere)."""

from __future__ import annotations

import os
from typing import Any
from typing import Mapping


def apply_presidio_regex_timeout(cfg: Mapping[str, Any]) -> None:
    """Set REGEX_TIMEOUT_SECONDS before Presidio import (read at module load).

    The value comes from ``[guardrails] regex_timeout_seconds`` in config.ini.
    """
    raw = cfg.get('regex_timeout_seconds')
    if raw is None or str(raw).strip() == '':
        raise ValueError('guardrails.regex_timeout_seconds is required in config.ini')
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise ValueError(
            f'guardrails.regex_timeout_seconds={raw!r} is not an integer'
        ) from exc
    if timeout < 1:
        raise ValueError(
            f'guardrails.regex_timeout_seconds={timeout} must be at least 1'
        )
    os.environ['REGEX_TIMEOUT_SECONDS'] = str(timeout)


def start_presidio_regex_timeout(timeout: str | None) -> None:
    """DI ``Resource`` hook: apply timeout from ``config.guardrails.regex_timeout_seconds``."""
    apply_presidio_regex_timeout({'regex_timeout_seconds': timeout})
