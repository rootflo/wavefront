import json
from api_services_module.execution.execute import execute_api_service


async def execute_api_service_fn(
    api_service_id: str,
    api_id: str,
    api_version: str = 'v1',
    **kwargs,  # Dynamic parameters for path_params, query_params, and payload
) -> str:
    """
    Execute an API service function.

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

    response = await execute_api_service(
        api_service_id=api_service_id,
        api_id=api_id,
        api_version=api_version,
        payload=payload if payload else None,
        query_params=query_params if query_params else None,
        path_params=path_params if path_params else None,
        headers=headers,
    )

    data = response.data
    if isinstance(data, str):
        return data
    if data is None:
        return ''
    try:
        return json.dumps(data)
    except TypeError:
        return str(data)
