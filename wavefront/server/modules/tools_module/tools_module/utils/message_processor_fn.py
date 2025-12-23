import json
from plugins_module.controllers.message_processor_controller import (
    execute_message_processor,
    ExecuteMessageProcessorPayload,
)


async def execute_message_processor_fn(message_processor_id: str, **kwargs) -> str:
    """Execute a message processor function

    Args:
        message_processor_id: UUID of the message processor to execute
        **kwargs: Dynamic parameters based on processor's input_schema

    Returns:
        Result from message processor execution as string
    """
    # Remove message_processor_id from kwargs (it's not part of input_data)
    input_data = {k: v for k, v in kwargs.items() if k != 'message_processor_id'}

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
