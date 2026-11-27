"""google-genai failures, from both Gemini and Vertex AI."""

from typing import Any, Optional

import httpx
from google.genai import errors as genai_errors

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.common import by_status, header_delay, seconds


def classify_gemini_error(exc: BaseException) -> Optional[Classification]:
    if not isinstance(exc, genai_errors.APIError):
        return None
    status = exc.code
    if status == 429 or exc.status == 'RESOURCE_EXHAUSTED':
        if _daily_quota(exc.details):
            return Classification('fatal', status)
        delay = _retry_delay(exc.details)
        if delay is None and isinstance(exc.response, httpx.Response):
            delay = header_delay(exc.response.headers)
        return Classification('rate_limit', status, delay)
    return by_status(status)


def _error_details(details: Any) -> list:
    error = details.get('error') if isinstance(details, dict) else None
    entries = error.get('details') if isinstance(error, dict) else None
    return _dicts(entries)


def _dicts(value: Any) -> list:
    """The dict entries of ``value``, or none when it isn't a list.

    The body is the provider's; a crash here would replace the 429 untyped.
    """
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _retry_delay(details: Any) -> Optional[float]:
    for entry in _error_details(details):
        if str(entry.get('@type', '')).endswith('RetryInfo'):
            return seconds(str(entry.get('retryDelay', '')).rstrip('s'))
    return None


def _daily_quota(details: Any) -> bool:
    for entry in _error_details(details):
        if str(entry.get('@type', '')).endswith('QuotaFailure'):
            for violation in _dicts(entry.get('violations')):
                if 'PerDay' in str(violation.get('quotaId', '')):
                    return True
    return False
