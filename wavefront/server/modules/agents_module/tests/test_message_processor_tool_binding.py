"""A message processor used as an agent tool must run with the API client bound.

Regression: the tool was built from the bare `execute_message_processor_fn`,
whose first parameter is the API client, so every call failed with
"missing 1 required positional argument: 'api'".
"""

from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from agents_module.services.agent_inference_service import AgentInferenceService

PROCESSOR_YAML = b"""
type: javascript
description: Look up an order
function:
  code: export default function(input) { return input; }
input_schema:
  required: [order_id]
  properties:
    order_id:
      type: string
      description: The order id
"""


def _service(function_registry):
    repository = AsyncMock()
    repository.find_one.return_value = SimpleNamespace(
        source='lookup.yaml', description='Look up an order'
    )
    storage = MagicMock()
    storage.read_file.return_value = PROCESSOR_YAML
    return AgentInferenceService(
        cache_manager=MagicMock(),
        tool_loader=SimpleNamespace(function_registry=function_registry),
        agent_crud_service=AsyncMock(),
        message_processor_repository=repository,
        cloud_storage_manager=storage,
        message_processor_bucket_name='bucket',
    )


async def test_the_tool_calls_through_the_bound_api_client():
    calls = []

    async def execute(api, /, message_processor_id: str, **kwargs):
        calls.append((api, message_processor_id, kwargs))
        return 'ok'

    api = object()
    service = _service({'trigger_message_processor': MethodType(execute, api)})

    tool = await service._try_load_message_processor_tool('order_lookup')
    result = await tool.execute(message_processor_id='p-1', order_id='A-1')

    assert result == 'ok'
    assert calls == [(api, 'p-1', {'order_id': 'A-1'})]
    assert set(tool.parameters) == {'message_processor_id', 'order_id'}


async def test_no_tool_when_the_registry_has_no_executor():
    service = _service({})

    assert await service._try_load_message_processor_tool('order_lookup') is None
