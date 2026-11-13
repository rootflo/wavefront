import asyncio
import json
from urllib.parse import quote

import flo_lib.http as httpx
from common_module.log.logger import logger

from tools_module.floware_api import FlowareApiClient

# BEHAVIOUR CHANGE (case assignment, CU-14yk43r7uck): this tool used to RAISE on every
# failure and, on success, return only the backend's `data` out of floware's envelope.
# It now returns the response body exactly as floware sent it, for success and failure
# alike, and never raises for a failed call.
#
# Why: a raise inside a function node fails the whole workflow run, and no edge can catch
# it, so a workflow had no way to carry on after a failed call. The underwriting pipeline
# needs exactly that: it pushes the automatic case assignment to the QMS middleware and,
# if the push fails, must still finish the run, just without assigning anyone. Returning
# the body untouched lets the workflow read whatever it needs from it.
#
# What callers see now:
#   - a proxied call (success or HTTP error): floware's envelope as-is,
#     {"meta": {"status": ..., "message": ...}, "data": <the backend's own body>}.
#     Fields that used to sit at the top level are now under `data`.
#   - floware's own errors (e.g. unknown service/API): its body, e.g. {"detail": ...}.
#   - no usable body (unreachable, timeout, non-JSON content): {"error": "..."}, the one
#     shape this tool makes up, because a downstream node needs JSON to read.
# Anything that relied on a failed call stopping the run must check the body itself;
# agents calling API tools get the body as text instead of an error.


# RETRIES (case assignment, CU-14yk43r7uck): opt-in per workflow node, off by default so
# existing nodes behave exactly as before. Set on the node's prefilled_params:
#   retry_enabled: true
#   max_retries: 5               # retries after the first attempt (0-10)
#   retry_window_seconds: 900    # total time spent WAITING between attempts (15 min)
# The waits double each time and add up to the window: first = window / (2^retries - 1).
# Only failures that can clear on their own are retried - nothing answered, a timeout,
# HTTP 408, 429 or 5xx. Any other answer, including 401/403/422, returns at once.
# The run (and its Celery worker) is held for up to max_hold_seconds(): the window plus
# one request timeout per attempt. The tool logs that figure when it starts retrying.
REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_WINDOW_SECONDS = 900
MAX_RETRIES_CAP = 10
RETRYABLE_STATUSES = frozenset({408, 429})


def retry_delays(max_retries: int, window_seconds: float) -> list[float]:
    """The wait before each retry: doubling, and adding up to window_seconds."""
    if max_retries <= 0:
        return []
    first = max(window_seconds, 0) / (2**max_retries - 1)
    return [first * 2**i for i in range(max_retries)]


def max_hold_seconds(max_retries: int, window_seconds: float) -> float:
    """Longest a node can hold its run: every wait plus every attempt timing out."""
    return max(window_seconds, 0) + (max(max_retries, 0) + 1) * REQUEST_TIMEOUT_SECONDS


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(value)


def _number(value, default, name: str) -> float:
    """A retry setting as a number; a bad value (null, 'abc') falls back to the default
    with a warning, so a misconfigured node cannot fail the run."""
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f'Invalid {name} {value!r}; using the default {default}')
        return float(default)


def _retryable(response) -> bool:
    """None = nothing answered (unreachable / timeout)."""
    if response is None:
        return True
    return response.status_code in RETRYABLE_STATUSES or response.status_code >= 500


def _error(message: str) -> str:
    """The only made-up output: used when there is no response body to pass on."""
    return json.dumps({'error': message})


async def execute_api_service_fn(
    api: FlowareApiClient,
    /,
    api_service_id: str,
    api_id: str,
    api_version: str = 'v1',
    retry_enabled: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_window_seconds: float = DEFAULT_RETRY_WINDOW_SECONDS,
    **kwargs,  # Dynamic parameters for path_params, query_params, and payload
) -> str:
    """
    Execute an API service via wavefront's own REST API
    (POST /v1/api-services/{api_service_id}/execute).

    Args:
        api_service_id: ID of the API service (prefilled)
        api_id: ID of the API endpoint (prefilled)
        api_version: API version (prefilled, default: v1)
        retry_enabled: retry transient failures with exponential backoff (default off)
        max_retries: retries after the first attempt, 0-10 (default 5)
        retry_window_seconds: total wait across all retries (default 900 = 15 min)
        **kwargs: Dynamic parameters including:
            - Payload schema fields (goes into payload)
            - Path parameters (prefixed with 'path_', goes into path_params)
            - Query parameters (prefixed with 'query_', goes into query_params)

    Returns:
        The response body exactly as floware sent it, success or failure; {"error": ...}
        only when there is no usable body. Never raises for a failed call. Before the
        case-assignment change it raised on failure and returned only `data` on success;
        see the note at the top of this module.
    """
    payload = {}
    path_params = {}
    query_params = {}

    # Extract special parameters if provided
    headers = kwargs.pop('headers', None)

    # Distribute remaining kwargs based on naming convention
    for key, value in kwargs.items():
        # Skip keys the workflow adds itself (not meant for the API)
        if key in ('node_outputs', 'input_list') or key.startswith('_wf_'):
            continue
        if key.startswith('path_'):
            # Path parameters prefixed with 'path_'
            path_params[key.replace('path_', '', 1)] = value
        elif key.startswith('query_'):
            # Query parameters prefixed with 'query_'
            query_params[key.replace('query_', '', 1)] = value
        else:
            # Everything else goes to payload
            payload[key] = value

    # Set default content-type
    if headers is None:
        headers = {}
    if not any(k.lower() == 'content-type' for k in headers.keys()):
        headers['content-type'] = 'application/json'

    url = f'{api.base_url}/floware/v1/api-services/{quote(api_service_id, safe="")}/execute'
    body = {
        'api_id': api_id,
        'api_version': api_version,
        'payload': payload if payload else None,
        'path_params': path_params,
        'query_params': query_params,
        'headers': headers,
    }
    retries = 0
    delays: list[float] = []
    if _as_bool(retry_enabled):
        retries = int(_number(max_retries, DEFAULT_MAX_RETRIES, 'max_retries'))
        retries = min(max(retries, 0), MAX_RETRIES_CAP)
        window = _number(
            retry_window_seconds, DEFAULT_RETRY_WINDOW_SECONDS, 'retry_window_seconds'
        )
        delays = retry_delays(retries, window)
        logger.info(
            f'API service {api_service_id}/{api_id}: retries on, up to {retries} over '
            f'{window / 60:.1f} min of waiting; this node can hold the run up to '
            f'~{max_hold_seconds(retries, window) / 60:.1f} min'
        )

    response = None
    request_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(retries + 1):
            try:
                response = await client.post(
                    url,
                    json=body,
                    headers=api.headers(),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                request_error = None
            except httpx.RequestError as e:
                response, request_error = None, e
            if not _retryable(response) or attempt == retries:
                break
            reason = (
                f'HTTP {response.status_code}'
                if response is not None
                else request_error
            )
            logger.warning(
                f'API service {api_service_id}/{api_id}: attempt {attempt + 1}/'
                f'{retries + 1} failed ({reason}); retrying in {delays[attempt]:.0f}s'
            )
            await asyncio.sleep(delays[attempt])

    if response is None:
        # Used to raise. Nothing answered, so there is no body to pass on.
        return _error(
            f'Failed to reach API service API for {api_service_id}/{api_id}: '
            f'{request_error}'
        )

    # Used to raise on HTTP errors, non-JSON, invalid JSON and a failed envelope, and to
    # return only `data` on success. Now any JSON body is passed on as-is; the workflow
    # reads meta/data to decide what happened.
    try:
        response.json()
    except (json.JSONDecodeError, ValueError):
        content_type = response.headers.get('content-type') or 'no'
        return _error(
            f'API service {api_service_id}/{api_id} answered {response.status_code} '
            f'with {content_type} content, not JSON'
        )
    return response.text
