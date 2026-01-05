"""Execute an API service by calling the backend through the proxy pipeline.

This function provides a programmatic way to execute API services, handling
authentication, routing, and transformation through the existing pipeline infrastructure.

Args:
    api_service_id: ID of the API service to execute
    api_id: ID of the specific API endpoint to call
    payload: Request payload/body to send
    path_params: Optional path parameters (e.g., {"id": "123"} for /users/{id})
    query_params: Optional query parameters
    headers: Optional custom headers to include in the request
    api_version: API version (default: "v1")

Returns:
    ProxyResponse object with meta (status, message, trace) and data

Example:
    >>> response = await execute_api_service(
    ...     api_service_id="crm-service",
    ...     api_id="get-user",
    ...     payload={"user_id": "123"},
    ...     path_params={"id": "123"}
    ... )
    >>> print(response.data)
"""

from typing import Dict, Any, Optional
from api_services_module.core.proxy import ApiProxy
from api_services_module.models.service import ProxyResponse
from dependency_injector.wiring import inject, Provide
from api_services_module.api_services_container import ApiServicesContainer


@inject
async def execute_api_service(
    api_service_id: str,
    api_id: str,
    payload: Optional[dict] = None,
    path_params: Optional[Dict[str, str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    api_version: str = 'v1',
    proxy: Optional[ApiProxy] = Provide[ApiServicesContainer.api_proxy],
) -> ProxyResponse:
    """
    Execute an API service by calling the backend through the proxy pipeline.

    Args:
        api_service_id: ID of the API service to execute
        api_id: ID of the specific API endpoint to call
        payload: Request payload/body to send
        path_params: Optional path parameters (e.g., {"id": "123"} for /users/{id})
        query_params: Optional query parameters
        headers: Optional custom headers to include in the request
        api_version: API version (default: "v1")
        proxy: Optional ApiProxy instance (if not provided, will need to be injected)

    Returns:
        ProxyResponse object with meta (status, message, trace) and data
    """
    if proxy is None:
        raise ValueError(
            'ApiProxy instance must be provided. '
            'This function should be called with a proxy instance injected from the container.'
        )

    # Process the request through the proxy pipeline
    response = await proxy.process_request(
        service_id=api_service_id,
        api_id=api_id,
        api_version=api_version,
        method='POST',  # Client always uses POST
        path='_workflow',  # Path is determined by the API configuration
        path_params=path_params or {},
        query_params=query_params or {},
        headers=headers or {},
        body=payload,
    )

    return response
