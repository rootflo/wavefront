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
    # Everything except the processor id is the processor's input_data, and it
    # arrives in two shapes at once:
    #   - nested under 'kwargs' when an upstream agent's parser wrapped the
    #     payload in a top-level `kwargs` object
    #   - flat, for workflow variables and the adapter's `node_outputs` key,
    #     which the adapter forwards because this function declares **kwargs
    # Both are merged so a processor can use either; nested wins on conflict,
    # preserving the behaviour of processors written against the old shape.
    #
    # `input_list` is dropped: it holds the same payloads as `node_outputs`, just
    # ungrouped, so forwarding both doubles the bytes the JS runtime has to
    # receive and parse — enough to blow its script timeout on a large document
    # set. A processor that needs ordering can read node_outputs, which is keyed
    # by producing node. (The passthrough node still gets input_list: it names
    # the parameter explicitly, so it is bound before this forwarding applies.)
    input_data = {
        k: v
        for k, v in kwargs.items()
        if k not in ('message_processor_id', 'input_list')
    }
    nested_input = input_data.get('kwargs') or {}
    flat_input = {k: v for k, v in input_data.items() if k != 'kwargs'}
    processor_input = (
        {**flat_input, **nested_input}
        if isinstance(nested_input, dict)
        else nested_input
    )

    body = {'input_data': processor_input}
    payload_bytes = len(json.dumps(body, default=str))

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
        # Name the processor and the payload size. A workflow can run several
        # processors, so "execution failed" on its own does not say which one —
        # and the usual causes (script timeout, memory) are size-driven, so the
        # byte count is the first thing worth knowing.
        raise Exception(
            f'Message processor {message_processor_id} execution failed '
            f'({payload_bytes:,} bytes sent, keys: {sorted(processor_input)}): '
            f'{error_msg}'
        )

    data = response_body.get('data')
    if data is None:
        raise Exception(
            f'Message processor {message_processor_id} response has no data field'
        )

    result = data.get('result')
    if result is None:
        raise Exception(
            f'Message processor {message_processor_id} response data has no '
            'result field'
        )

    return result
