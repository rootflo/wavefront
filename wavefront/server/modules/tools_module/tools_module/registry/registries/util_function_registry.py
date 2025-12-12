from tools_module.utils.message_processor_fn import execute_message_processor_fn
from tools_module.utils.api_service_fn import execute_api_service_fn

UTIL_FUNCTION_REGISTRY = {
    'message_processor': execute_message_processor_fn,
    'rf_api_service': execute_api_service_fn,
}
