"""Helpers the provider classifiers share."""

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping, Optional

from flo_ai.llm.rate_limits.models import Classification


def by_status(status: Optional[int]) -> Classification:
    """A failure that isn't a rate limit: 5xx and 408 are transient."""
    if status is not None and (status >= 500 or status == 408):
        return Classification('transient', status)
    return Classification('fatal', status)


def classify_sdk_status_error(exc: Any) -> Classification:
    """An OpenAI or Anthropic SDK status error; both SDKs share its shape.

    529 counts as a rate limit through either SDK: a proxy can pass
    Anthropic's overload status through the OpenAI one.
    """
    status = exc.status_code
    if status == 429:
        # Billing exhausted; waiting can't help.
        if getattr(exc, 'code', None) == 'insufficient_quota':
            return Classification('fatal', status)
        return Classification('rate_limit', status, header_delay(exc.response.headers))
    if status == 529:
        return Classification('rate_limit', status, header_delay(exc.response.headers))
    if status == 409:
        # A lock timeout; the SDKs retried it before their retries were turned off.
        return Classification('transient', status)
    return by_status(status)


def seconds(value: Any) -> Optional[float]:
    """``value`` as a non-negative, finite number, or None if it isn't one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # float() accepts 'inf': an endless wait would close the shared gate for good.
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def header_delay(headers: Mapping[str, str]) -> Optional[float]:
    """Seconds from ``retry-after-ms`` or ``retry-after`` (seconds or HTTP-date)."""
    ms = seconds(headers.get('retry-after-ms'))
    if ms is not None:
        return ms / 1000

    value = headers.get('retry-after')
    if value is None:
        return None
    delay = seconds(value)
    if delay is not None:
        return delay
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
