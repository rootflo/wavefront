"""The internal execute endpoint runs one API by id for workflow and agent tools."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from api_services_module.core.router import ProxyRouter
from api_services_module.models.service import ProxyResponse


@pytest.fixture
def proxy():
    proxy = Mock()
    proxy.process_request = AsyncMock(
        return_value=ProxyResponse.success(data={'id': 42})
    )
    return proxy


@pytest.fixture
def client(proxy, mock_response_formatter):
    registry = Mock()
    registry.get_all_services.return_value = {}
    router = ProxyRouter(proxy, registry, mock_response_formatter)
    app = FastAPI()
    app.include_router(router.get_router())
    return TestClient(app)


def test_runs_the_api_with_the_body_fields(client, proxy):
    response = client.post(
        '/v1/api-services/crm/execute',
        json={
            'api_id': 'get-user',
            'api_version': 'v2',
            'payload': {'name': 'Ada'},
            'path_params': {'user_id': '42'},
            'query_params': {'page': 3},
            'headers': {'X-Tenant': 'acme'},
        },
    )

    assert response.status_code == 200
    assert response.json()['data'] == {'id': 42}
    proxy.process_request.assert_awaited_once_with(
        service_id='crm',
        api_id='get-user',
        api_version='v2',
        method='POST',
        path='_workflow',
        path_params={'user_id': '42'},
        query_params={'page': 3},
        headers={'X-Tenant': 'acme'},
        body={'name': 'Ada'},
        restrict_payload_to_schema=True,
    )


def test_request_headers_are_not_forwarded_to_the_backend(client, proxy):
    client.post(
        '/v1/api-services/crm/execute',
        json={'api_id': 'get-user'},
        headers={'X-Passthrough': 's3cret', 'X-Forwarded-Client-Cert': 'spiffe://x'},
    )

    assert proxy.process_request.await_args.kwargs['headers'] == {}


def test_the_proxy_status_code_is_returned(client, proxy):
    proxy.process_request.return_value = ProxyResponse.error(
        message='Pipeline error: boom', http_status_code=502
    )

    response = client.post('/v1/api-services/crm/execute', json={'api_id': 'x'})

    assert response.status_code == 502
    assert response.json()['meta']['message'] == 'Pipeline error: boom'


def test_binary_responses_pass_through(client, proxy):
    proxy.process_request.return_value = Response(
        content=b'\x89PNG', media_type='image/png'
    )

    response = client.post('/v1/api-services/crm/execute', json={'api_id': 'img'})

    assert response.headers['content-type'] == 'image/png'
    assert response.content == b'\x89PNG'


class TestRestrictPayloadToSchema:
    """The proxy side of the endpoint: only declared fields reach the backend."""

    @pytest.fixture
    def run(self):
        from api_services_module.core.proxy import ApiProxy
        from api_services_module.models.service import (
            ApiConfig,
            HttpMethod,
            PayloadFieldSchema,
            PayloadSchema,
            ServiceDefinition,
        )

        schema = PayloadSchema(fields=[PayloadFieldSchema(name='name', type='string')])
        service = ServiceDefinition(
            id='crm',
            base_url='https://crm.test',
            auth=None,  # the pipeline is stubbed, so auth is never built
            apis=[
                ApiConfig(
                    id='create-user',
                    path='/users',
                    backend_path='/users',
                    method=HttpMethod.POST,
                    version='v1',
                    payload_schema=schema,
                ),
                ApiConfig(
                    id='free-form',
                    path='/free',
                    backend_path='/free',
                    method=HttpMethod.POST,
                    version='v1',
                ),
            ],
        )
        registry = Mock()
        registry.get_all_services.return_value = {}
        registry.get_service.return_value = service
        proxy = ApiProxy(registry)

        sent = {}

        async def execute(context):
            sent['body'] = context.body
            return context

        pipeline = Mock()
        pipeline.execute = execute
        proxy._get_or_build_pipeline = Mock(return_value=pipeline)

        async def run(api_id, body, restrict):
            await proxy.process_request(
                service_id='crm',
                api_id=api_id,
                body=body,
                restrict_payload_to_schema=restrict,
            )
            return sent['body']

        return run

    async def test_undeclared_fields_are_dropped(self, run):
        body = {'name': 'Ada', 'upstream_field': 1, 'tenant': 'acme'}

        assert await run('create-user', body, restrict=True) == {'name': 'Ada'}

    async def test_nothing_declared_left_sends_no_body(self, run):
        assert await run('create-user', {'other': 1}, restrict=True) is None

    async def test_api_without_a_schema_gets_everything(self, run):
        body = {'name': 'Ada', 'tenant': 'acme'}

        assert await run('free-form', body, restrict=True) == body

    async def test_public_route_is_not_filtered(self, run):
        body = {'name': 'Ada', 'tenant': 'acme'}

        assert await run('create-user', body, restrict=False) == body
