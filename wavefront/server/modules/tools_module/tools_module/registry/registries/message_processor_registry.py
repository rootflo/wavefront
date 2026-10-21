"""
Message Processor Tools Registry

Contains the mapping from message processor tool names to their execution function.
Since all message processors use the same execution function (with different IDs),
this registry uses a single trigger function.
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.floware_api import FlowareApiClient
from tools_module.utils.message_processor_fn import execute_message_processor_fn


def build_message_processor_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    # For message processors, we use a single execution function
    # The actual processor is selected via the message_processor_id parameter
    return {
        'trigger_message_processor': MethodType(execute_message_processor_fn, api),
    }
