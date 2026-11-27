"""FlowareLlmConfigClient asks floware for the plaintext config on the service
path: include_secrets, never an Authorization header, passthrough only
outside production."""

import functools
import uuid

import flo_lib.http as httpx
import pytest

from llm_inference_config_module.clients import floware_llm_config_client
from llm_inference_config_module.clients.floware_llm_config_client import (
    FlowareLlmConfigClient,
)

CONFIG_ID = uuid.uuid4()
CONFIG = {'id': str(CONFIG_ID), 'llm_model': 'gpt-4o', 'api_key': 'sk-live-123'}


@pytest.fixture
def floware(monkeypatch):
    """Route the client's requests to a handler and record them."""
    requests = []
    responses = {'status': 200, 'json': {'meta': {}, 'data': CONFIG}}

    def handler(request):
        requests.append(request)
        return httpx.Response(responses['status'], json=responses['json'])

    monkeypatch.setattr(
        floware_llm_config_client.httpx,
        'AsyncClient',
        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )
    return requests, responses


async def test_fetches_the_plaintext_config_with_include_secrets(floware):
    requests, _ = floware
    client = FlowareLlmConfigClient('http://floware:8001/', 'shh', 'dev')

    assert await client.get_runtime_config(CONFIG_ID) == CONFIG

    (request,) = requests
    assert request.method == 'GET'
    assert request.url.path == f'/floware/v1/llm-inference-configs/{CONFIG_ID}'
    assert request.url.params['include_secrets'] == 'true'
    assert request.headers['X-Passthrough'] == 'shh'
    assert 'authorization' not in request.headers


async def test_no_passthrough_in_production(floware):
    requests, _ = floware
    client = FlowareLlmConfigClient('http://floware:8001', 'shh', 'production')

    await client.get_runtime_config(CONFIG_ID)

    assert 'x-passthrough' not in requests[0].headers
    assert 'authorization' not in requests[0].headers


async def test_no_passthrough_without_a_secret(floware):
    requests, _ = floware
    client = FlowareLlmConfigClient('http://floware:8001', '', 'dev')

    await client.get_runtime_config(CONFIG_ID)

    assert 'x-passthrough' not in requests[0].headers


async def test_missing_config_is_none(floware):
    _, responses = floware
    responses.update(status=404, json={'meta': {'error': 'not found'}})
    client = FlowareLlmConfigClient('http://floware:8001', 'shh', 'dev')

    assert await client.get_runtime_config(CONFIG_ID) is None


async def test_other_errors_raise(floware):
    _, responses = floware
    responses.update(status=403, json={'meta': {'error': 'forbidden'}})
    client = FlowareLlmConfigClient('http://floware:8001', 'shh', 'dev')

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_runtime_config(CONFIG_ID)
