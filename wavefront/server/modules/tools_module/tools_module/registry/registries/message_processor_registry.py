"""
Message Processor Tools Registry

Contains the mapping from message processor tool names to their execution function.
Since all message processors use the same execution function (with different IDs),
this registry uses a single trigger function.
"""

from tools_module.utils.message_processor_fn import execute_message_processor_fn


# For message processors, we use a single execution function
# The actual processor is selected via the message_processor_id parameter
MESSAGE_PROCESSOR_REGISTRY = {
    'trigger_message_processor': execute_message_processor_fn,
}
