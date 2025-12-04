from typing import Dict, Any
import json
from plugins_module.controllers.message_processor_controller import (
    execute_message_processor,
    ExecuteMessageProcessorPayload,
)


async def execute_message_processor_fn(
    message_processor_id: str,
    input_data: Dict[str, Any],
) -> str:
    """Process a message using the message processor function

    Args:
        message_processor_id: The ID of the message processor to execute
        input_data: The input data to pass to the message processor (dict of key-value pairs)

    Returns:
        The result from the message processor execution as a string
    """

    payload = ExecuteMessageProcessorPayload(input_data=input_data)
    response = await execute_message_processor(message_processor_id, payload)

    response_body_bytes = response.body
    response_body = json.loads(response_body_bytes.decode('utf-8'))

    # Check if there's an error in the response
    meta = response_body.get('meta', {})
    if meta.get('status') == 'failure':
        error_msg = meta.get('error', 'Unknown error')
        raise Exception(f'Message processor execution failed: {error_msg}')

    data = response_body.get('data')
    if data is None:
        raise Exception('Message processor response has no data field')

    result = data.get('result')
    if result is None:
        raise Exception('Message processor response data has no result field')

    return result
