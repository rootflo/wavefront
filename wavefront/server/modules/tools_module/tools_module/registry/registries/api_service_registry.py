"""
API Service Tools Registry

Contains the mapping from API service tool names to their execution function.
Since all API services use the same execution function (with different IDs),
this registry uses a single trigger function.
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.floware_api import FlowareApiClient
from tools_module.utils.api_service_fn import execute_api_service_fn


def build_api_service_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    # For API services, we use a single execution function
    # The actual service and API are selected via the api_service_id and api_id parameters
    return {
        'trigger_api_service': MethodType(execute_api_service_fn, api),
    }
