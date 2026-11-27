"""Plain HTTP and timeout failures, from providers called without an SDK (Ollama)."""

import asyncio
from typing import Optional

import aiohttp
import httpx

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.common import by_status, header_delay


def classify_http_error(exc: BaseException) -> Optional[Classification]:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return Classification('rate_limit', status, header_delay(exc.response.headers))
        return by_status(status)

    if isinstance(exc, aiohttp.ClientResponseError):
        if exc.status == 429:
            return Classification('rate_limit', exc.status, header_delay(exc.headers or {}))
        return by_status(exc.status)

    if isinstance(
        exc,
        (
            httpx.TransportError,
            aiohttp.ClientConnectionError,
            asyncio.TimeoutError,
            TimeoutError,
        ),
    ):
        return Classification('transient')

    return None
