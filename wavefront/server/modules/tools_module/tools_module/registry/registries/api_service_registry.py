"""
API Service Tools Registry

Contains the mapping from API service tool names to their execution function.
Since all API services use the same execution function (with different IDs),
this registry uses a single trigger function.
"""

from tools_module.utils.api_service_fn import execute_api_service_fn


# For API services, we use a single execution function
# The actual service and API are selected via the api_service_id and api_id parameters
API_SERVICE_REGISTRY = {
    'trigger_api_service': execute_api_service_fn,
}
