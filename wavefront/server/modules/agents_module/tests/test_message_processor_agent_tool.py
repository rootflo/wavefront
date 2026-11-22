"""Message processors loaded as agent tools must run with the floware client bound."""

from unittest.mock import AsyncMock, Mock, patch

import yaml

from agents_module.services.agent_inference_service import AgentInferenceService
from tools_module.floware_api import FlowareApiClient
from tools_module.registry.function_registry import build_function_registry
from tools_module.registry.tool_loader import ToolLoader

PROCESSOR_YAML = yaml.safe_dump(
    {
        'description': 'Summarise a document',
        'input_schema': {'properties': {'text': {'type': 'string'}}},
    }
)


def make_service() -> AgentInferenceService:
    service = object.__new__(AgentInferenceService)
    service.tool_loader = ToolLoader(
        function_registry=build_function_registry(FlowareApiClient('http://floware'))
    )
    service.message_processor_repository = AsyncMock(
        find_one=AsyncMock(return_value=Mock(source='summarise.yaml', description=''))
    )
    service.cloud_storage_manager = Mock(
        read_file=Mock(return_value=PROCESSOR_YAML.encode())
    )
    service.message_processor_bucket_name = 'bucket'
    return service


async def test_message_processor_tool_runs_with_api_bound():
    tool = await make_service()._try_load_message_processor_tool('summarise')
    assert tool is not None

    response = Mock(status_code=200)
    response.json.return_value = {'meta': {}, 'data': {'result': 'summary'}}
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__.return_value = client
    with patch(
        'tools_module.utils.message_processor_fn.httpx.AsyncClient',
        return_value=client,
    ):
        result = await tool.run(inputs=[], message_processor_id='mp-1', text='hello')

    assert result == 'summary'
    url = client.post.await_args[0][0]
    assert url == 'http://floware/floware/v1/message-processors/mp-1/execute'
    assert client.post.await_args[1]['json'] == {'input_data': {'text': 'hello'}}
