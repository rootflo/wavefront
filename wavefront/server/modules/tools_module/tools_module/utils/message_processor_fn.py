import json
import os

import httpx

FLOWARE_BASE_URL = os.getenv('FLOWARE_BASE_URL', 'http://localhost:8001').rstrip('/')


async def execute_message_processor_fn(message_processor_id: str, **kwargs) -> str:
    """Execute a deployed message processor via wavefront's own REST API
    (POST /v1/message-processors/{processor_id}/execute).

    Args:
        message_processor_id: UUID of the message processor to execute
        **kwargs: Dynamic parameters based on the processor's input_schema

    Returns:
        Result from message processor execution as string
    """
    # Everything except the processor id is the processor's input_data. The
    # function-node adapter passes the actual inputs under a 'kwargs' key; fall
    # back to the flat params if that key isn't present.
    input_data = {k: v for k, v in kwargs.items() if k != 'message_processor_id'}
    processor_input = input_data.get('kwargs', input_data)

    url = (
        f'{FLOWARE_BASE_URL}/floware/v1/message-processors/'
        f'{message_processor_id}/execute'
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json={'input_data': processor_input}, timeout=60.0
            )
        except httpx.RequestError as e:
            raise Exception(
                f'Failed to reach message processor API for '
                f'{message_processor_id}: {e}'
            )

    try:
        response_body = response.json()
    except json.JSONDecodeError:
        raise Exception(
            f'Message processor {message_processor_id} returned non-JSON '
            f'({response.status_code}): {response.text}'
        )

    meta = response_body.get('meta', {})
    if response.status_code != 200 or meta.get('status') == 'failure':
        error_msg = meta.get('error', response.text)
        raise Exception(f'Message processor execution failed: {error_msg}')

    data = response_body.get('data')
    if data is None:
        raise Exception('Message processor response has no data field')

    result = data.get('result')
    if result is None:
        raise Exception('Message processor response data has no result field')

    return result
