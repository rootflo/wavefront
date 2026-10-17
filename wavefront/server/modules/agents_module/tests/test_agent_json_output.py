"""The v2 API must fail when requested JSON is absent from a model reply."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flo_ai import Agent, BaseLLM

from agents_module.controllers import agent_controller
from agents_module.agents_container import AgentsContainer
from common_module.common_container import CommonContainer
from agents_module.services.agent_inference_service import AgentInferenceService


@pytest.fixture
def inference_api():
    llm = Mock(spec=BaseLLM)
    llm.generate = AsyncMock()
    llm.get_message_content.side_effect = lambda response: response
    service = object.__new__(AgentInferenceService)
    service.prepare_agent_v2 = AsyncMock()

    async def perform(**kwargs):
        agent, namespace, name = await service.prepare_agent_v2()
        result, elapsed = await service.run_agent_inference(
            agent,
            kwargs['inputs'],
            kwargs['variables'],
            name,
            kwargs['output_json_enabled'],
        )
        return result, elapsed, namespace

    service.perform_inference_v2 = perform
    agents = AgentsContainer()
    common = CommonContainer()
    agents.agent_inference_service.override(service)
    agents.wire(modules=[agent_controller])
    common.wire(modules=[agent_controller])
    app = FastAPI()
    app.include_router(agent_controller.agents_router, prefix='/floware')
    try:
        with TestClient(app) as client:
            yield client, service, llm
    finally:
        agents.unwire()
        common.unwire()


def reply(service, llm, content, output_schema=None):
    llm.generate.return_value = content
    agent = Agent(
        name='test',
        system_prompt='Answer the user',
        llm=llm,
        output_schema=output_schema,
    )
    service.prepare_agent_v2.return_value = agent, 'default', 'test'


@pytest.mark.parametrize('content', ['The customer is Alice.', '', '{broken json}'])
def test_missing_json_fails(inference_api, content):
    client, service, llm = inference_api
    reply(service, llm, content)
    response = client.post(
        f'/floware/v2/agents/{uuid4()}/inference',
        json={'inputs': [{'role': 'user', 'content': 'Who?'}]},
    )
    assert response.status_code == 502
    assert response.json()['meta']['status'] == 'failure'
    assert 'JSON' in response.json()['meta']['error']
    if content:
        assert content not in response.json()['meta']['error']
    llm.generate.assert_awaited_once()


@pytest.mark.parametrize(
    ('content', 'expected'),
    [
        ('{"name": "Alice"}', {'name': 'Alice'}),
        ('{}', {}),
        ('```json\n{"name": "Alice"}\n```', {'name': 'Alice'}),
        ('{"name": "Alice"} and {"age": 20}', {'name': 'Alice', 'age': 20}),
    ],
)
def test_valid_json_preserved(inference_api, content, expected):
    client, service, llm = inference_api
    reply(service, llm, content)
    response = client.post(
        f'/floware/v2/agents/{uuid4()}/inference', json={'inputs': 'Who?'}
    )
    assert response.status_code == 201
    assert response.json()['data']['data']['result'] == expected


def test_plain_text_mode_preserved(inference_api):
    client, service, llm = inference_api
    content = 'The customer is Alice.'
    reply(service, llm, content)
    response = client.post(
        f'/floware/v2/agents/{uuid4()}/inference',
        json={'inputs': 'Who?', 'output_json_enabled': False},
    )
    assert response.status_code == 201
    assert response.json()['data']['data']['result'] == content


def test_parser_output_preserved(inference_api):
    client, service, llm = inference_api
    schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}}
    reply(service, llm, '{"name": "Alice"}', output_schema=schema)
    response = client.post(
        f'/floware/v2/agents/{uuid4()}/inference', json={'inputs': 'Who?'}
    )
    assert response.status_code == 201
    assert response.json()['data']['data']['result'] == {'name': 'Alice'}
    assert llm.generate.await_args.kwargs['output_schema'] == schema
