import json
from typing import Optional, Dict, Any
from api_services_module.execution.execute import execute_api_service


async def execute_api_service_fn(
    api_service_id: str,
    api_id: str,
    api_version: str = 'v1',
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    path_params: Optional[Dict[str, Any]] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """Process a message using the message processor function"""

    headers = headers or {}
    if not any(k.lower() == 'content-type' for k in headers.keys()):
        headers['content-type'] = 'application/json'

    response = await execute_api_service(
        api_service_id=api_service_id,
        api_id=api_id,
        api_version=api_version,
        payload=payload,
        query_params=query_params,
        path_params=path_params,
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
