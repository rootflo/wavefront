from types import MethodType
from typing import Callable, Dict

from tools_module.floware_api import FlowareApiClient
from tools_module.utils.message_processor_fn import execute_message_processor_fn
from tools_module.utils.api_service_fn import execute_api_service_fn
from tools_module.utils.passthrough_fn import passthrough


def build_util_function_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    return {
        'message_processor': MethodType(execute_message_processor_fn, api),
        'rf_api_service': execute_api_service_fn,
        'passthrough': passthrough,
    }
