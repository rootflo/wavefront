"""HTTP calls to the inference app, shared by the text and image clients."""

import time
from typing import Any

import httpx
from flo_utils.utils.log import logger

# Status codes that mean "try again shortly" rather than "this request is bad":
# 429 rate limited, 503 model still loading, 502/504 gateway trouble.
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

# Upper bound on how long a Retry-After header can make us wait.
MAX_RETRY_AFTER_SECONDS = 60.0


def post_with_retry(
    client: httpx.Client,
    url: str,
    payload: dict,
    max_retries: int = 3,
    initial_delay: float = 1.0,
) -> Any:
    """POST JSON and return the decoded response body.

    Connection failures and 429/502/503/504 are retried with backoff; a
    Retry-After header, when present, sets the minimum wait before the next
    attempt. Other HTTP errors raise httpx.HTTPStatusError straight away. Read
    timeouts are not retried: the service is still working on the request,
    and re-sending it would only add to its queue.
    """
    delay = initial_delay
    last_error: Exception = RuntimeError(f'No attempt made to call {url}')
    for attempt in range(1, max_retries + 1):
        wait = delay
        try:
            response = client.post(url, json=payload)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response.json()
            last_error = httpx.HTTPStatusError(
                f'{response.status_code} from inference service',
                request=response.request,
                response=response,
            )
            wait = max(wait, retry_after_seconds(response))
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
        ) as err:
            last_error = err
        if attempt < max_retries:
            logger.warning(
                f'Inference call to {url} failed (attempt {attempt}/'
                f'{max_retries}): {last_error}; retrying in {wait:.1f}s'
            )
            time.sleep(wait)
            delay *= 1.5
    raise last_error


def retry_after_seconds(response: httpx.Response) -> float:
    """Seconds from a Retry-After header (capped), or 0 if absent/invalid."""
    try:
        seconds = float(response.headers.get('Retry-After', 0))
    except ValueError:
        return 0.0
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
