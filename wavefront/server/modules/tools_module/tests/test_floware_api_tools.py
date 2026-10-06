"""Tools reach floware through an injected FlowareApiClient, not module state.

Each registry function is bound to the client its container built, so two
containers (or two clients in one test) can point at different floware
instances without affecting each other.
"""

import json
from types import MethodType

import httpx
import pytest
from flo_ai.models import UserMessage

from tools_module.floware_api import FlowareApiClient
from tools_module.registry.function_node_adapter import (
    create_function_node_adapter,
    get_function_node_adapter,
)
from tools_module.registry.function_registry import build_function_registry
from tools_module.registry.tool_loader import ToolLoader
from tools_module.tools_container import ToolsContainer


@pytest.fixture
def http(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        reply = staticmethod(lambda request: httpx.Response(200, json={}))

    def dispatch(request: httpx.Request) -> httpx.Response:
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.reply(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


class TestFlowareApiClient:
    def test_trailing_slash_is_stripped(self):
        assert (
            FlowareApiClient('http://floware:8001/').base_url == 'http://floware:8001'
        )

    def test_headers_carry_passthrough_secret(self):
        api = FlowareApiClient('http://f', passthrough_secret='s3cret')

        assert api.headers() == {
            'Content-Type': 'application/json',
            'X-Passthrough': 's3cret',
        }

    @pytest.mark.parametrize('secret', [None, ''])
    def test_headers_without_secret(self, secret):
        api = FlowareApiClient('http://f', passthrough_secret=secret)

        assert api.headers() == {'Content-Type': 'application/json'}

    def test_is_immutable(self):
        api = FlowareApiClient('http://f')

        with pytest.raises(Exception):
            api.base_url = 'http://other'


class TestBuildFunctionRegistry:
    def test_floware_tools_are_bound_to_the_client(self):
        api = FlowareApiClient('http://f')
        registry = build_function_registry(api)

        for name in (
            'datasource_insert_rows',
            'datasource_insert_multi',
            'datasource_execute_query',
            'send_email',
            'fetch_configuration',
            'message_processor',
            'trigger_message_processor',
        ):
            assert isinstance(registry[name], MethodType), name
            assert registry[name].__self__ is api, name

    def test_tools_that_do_not_call_floware_stay_unbound(self):
        registry = build_function_registry(FlowareApiClient('http://f'))

        for name in ('rf_api_service', 'passthrough', 'trigger_api_service'):
            assert not isinstance(registry[name], MethodType), name

    def test_bound_tools_keep_their_name_and_docstring(self):
        registry = build_function_registry(FlowareApiClient('http://f'))

        assert registry['send_email'].__name__ == 'send_email'
        assert 'Send an email' in registry['send_email'].__doc__

    def test_registries_are_independent_per_client(self):
        first = build_function_registry(FlowareApiClient('http://one'))
        second = build_function_registry(FlowareApiClient('http://two'))

        assert first['send_email'].__self__.base_url == 'http://one'
        assert second['send_email'].__self__.base_url == 'http://two'


class TestToolsUseTheirClient:
    async def test_fetch_configuration_uses_base_url(self, http):
        http.reply = lambda request: httpx.Response(200, json={'data': {'limit': 5}})
        registry = build_function_registry(FlowareApiClient('http://one/'))

        result = await registry['fetch_configuration']('acme dev', 'thresholds')

        assert json.loads(result) == {'limit': 5}
        (request,) = http.requests
        assert str(request.url) == (
            'http://one/floware/v1/configurations/acme%20dev/thresholds'
        )

    async def test_two_clients_hit_their_own_hosts(self, http):
        http.reply = lambda request: httpx.Response(200, json={'data': {}})
        first = build_function_registry(FlowareApiClient('http://one'))
        second = build_function_registry(FlowareApiClient('http://two'))

        await first['fetch_configuration']('ns', 'k')
        await second['fetch_configuration']('ns', 'k')

        assert [r.url.host for r in http.requests] == ['one', 'two']

    async def test_send_email_sends_passthrough_header(self, http):
        registry = build_function_registry(
            FlowareApiClient('http://one', passthrough_secret='s3cret')
        )

        result = await registry['send_email']('conn-1', 'a@b.c', 'Hi', 'Body')

        assert result == 'Email sent to a@b.c.'
        (request,) = http.requests
        assert request.url.path == '/floware/v1/email-connections/conn-1/send'
        assert request.headers['X-Passthrough'] == 's3cret'
        assert json.loads(request.content) == {
            'to': ['a@b.c'],
            'subject': 'Hi',
            'body': 'Body',
        }

    async def test_send_email_without_secret_omits_header(self, http):
        registry = build_function_registry(FlowareApiClient('http://one'))

        await registry['send_email']('conn-1', 'a@b.c', 'Hi', 'Body')

        assert 'X-Passthrough' not in http.requests[0].headers


class TestFunctionNodeAdapterWithBoundTools:
    async def test_adapter_calls_bound_function_with_declared_params(self, http):
        http.reply = lambda request: httpx.Response(200, json={'data': {'ok': 1}})
        registry = build_function_registry(FlowareApiClient('http://one'))
        adapter = create_function_node_adapter(
            registry['fetch_configuration'], 'fetch_configuration'
        )

        result = await adapter(
            inputs=[UserMessage(content='run')], namespace='ns', key='k'
        )

        assert json.loads(result) == {'ok': 1}
        assert http.requests[0].url.host == 'one'

    async def test_message_processor_forwards_params_without_the_client(self, http):
        http.reply = lambda request: httpx.Response(
            200, json={'meta': {'status': 'success'}, 'data': {'result': 'done'}}
        )
        registry = build_function_registry(FlowareApiClient('http://one'))
        adapter = create_function_node_adapter(
            registry['message_processor'], 'message_processor'
        )

        result = await adapter(
            inputs=[UserMessage(content='{"amount": 3}')],
            message_processor_id='mp-1',
            # a workflow parameter that happens to share the client's name
            api='workflow-value',
        )

        assert result == 'done'
        (request,) = http.requests
        assert request.url.path == '/floware/v1/message-processors/mp-1/execute'
        sent = json.loads(request.content)['input_data']
        assert sent['amount'] == 3
        assert sent['api'] == 'workflow-value'
        assert 'message_processor_id' not in sent

    def test_lookup_uses_the_given_registry(self):
        registry = build_function_registry(FlowareApiClient('http://one'))

        assert get_function_node_adapter('send_email', registry) is not None
        assert get_function_node_adapter('nope', registry) is None


class TestToolLoader:
    def test_loads_tools_from_the_injected_registry(self):
        registry = build_function_registry(FlowareApiClient('http://one'))
        loader = ToolLoader(function_registry=registry)

        tool = loader.load_tool('send_email')

        assert tool is not None
        assert tool.function is registry['send_email']

    def test_unregistered_tool_is_not_loaded(self):
        loader = ToolLoader(function_registry={})

        assert loader.load_tool('send_email') is None

    def test_function_node_registry_adapts_every_function_once(self):
        registry = build_function_registry(FlowareApiClient('http://one'))
        loader = ToolLoader(function_registry=registry)

        nodes = loader.function_node_registry

        assert set(nodes) == set(registry)
        assert loader.function_node_registry is nodes


class TestToolsContainer:
    def test_wires_client_registry_and_loader(self):
        container = ToolsContainer(
            datasource_repository=None,
            email_connection_repository=None,
            message_processor_repository=None,
            api_services_manager=None,
            cloud_storage_manager=None,
            message_processor_bucket_name='bucket',
            floware_base_url='http://floware:8001/',
            passthrough_secret='s3cret',
        )

        api = container.floware_api()
        loader = container.tool_loader()

        assert api.base_url == 'http://floware:8001'
        assert api.passthrough_secret == 's3cret'
        assert loader.function_registry['send_email'].__self__ is api
