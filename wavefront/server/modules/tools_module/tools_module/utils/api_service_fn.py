import json
from urllib.parse import quote

import flo_lib.http as httpx

from tools_module.floware_api import FlowareApiClient


def _error_message(response) -> str:
    """The proxy's own error text, or '' if the body carries none.

    A pipeline failure comes back as ``{"meta": {"status": ..., "message": ...}}``;
    a missing service or API is a FastAPI ``HTTPException``, ``{"detail": ...}``.
    """
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return ''
    if not isinstance(body, dict):
        return ''
    meta = body.get('meta') or {}
    return meta.get('message') or meta.get('error') or body.get('detail') or ''


async def execute_api_service_fn(
    api: FlowareApiClient,
    /,
    api_service_id: str,
    api_id: str,
    api_version: str = 'v1',
    **kwargs,  # Dynamic parameters for path_params, query_params, and payload
) -> str:
    """
    Execute an API service via wavefront's own REST API
    (POST /v1/api-services/{api_service_id}/execute).

    Args:
        api_service_id: ID of the API service (prefilled)
        api_id: ID of the API endpoint (prefilled)
        api_version: API version (prefilled, default: v1)
        **kwargs: Dynamic parameters including:
            - Payload schema fields (goes into payload)
            - Path parameters (prefixed with 'path_', goes into path_params)
            - Query parameters (prefixed with 'query_', goes into query_params)

    Returns:
        Result from API service execution as string
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
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json=body, headers=api.headers(), timeout=60.0
            )
        except httpx.RequestError as e:
            raise Exception(
                f'Failed to reach API service API for {api_service_id}/{api_id}: {e}'
            )

    # Raise so a failure is not mistaken for an empty result
    if response.status_code >= 400:
        detail = _error_message(response) or response.text
        raise Exception(
            f'API service {api_service_id}/{api_id} failed '
            f'({response.status_code}): {detail}'
        )

    # Non-JSON means a binary response passed through unwrapped
    content_type = response.headers.get('content-type', '')
    if content_type.split(';')[0].strip().lower() != 'application/json':
        raise Exception(
            f'API service {api_service_id}/{api_id} returned {content_type or "no"} '
            'content, which this tool does not support'
        )

    try:
        response_body = response.json()
    except json.JSONDecodeError:
        raise Exception(
            f'API service {api_service_id}/{api_id} returned invalid JSON: '
            f'{response.text}'
        )

    meta = response_body.get('meta') or {}
    if meta.get('status') != 'success':
        detail = _error_message(response) or response.text
        raise Exception(f'API service {api_service_id}/{api_id} failed: {detail}')

    data = response_body.get('data')
    if isinstance(data, str):
        return data
    if data is None:
        return ''
    try:
        return json.dumps(data)
    except TypeError:
        return str(data)
