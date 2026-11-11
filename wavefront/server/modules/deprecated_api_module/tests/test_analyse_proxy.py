"""/v1/image/analyse relays the caller's request unchanged to the audit
API service and hands its response back as-is."""

import httpx
import pytest
from common_module.common_container import CommonContainer
from fastapi import FastAPI
from fastapi.testclient import TestClient
from deprecated_api_module.controllers.router import deprecated_api_router
from deprecated_api_module.deprecated_api_container import DeprecatedApiContainer
from deprecated_api_module.services import audit_service_proxy as proxy_module

BASE_URL = 'http://floware.internal:8001'
AUDIT_URL = f'{BASE_URL}/floware/v1/api-services/gold-audit-service/apis/v1/audit'


@pytest.fixture
def upstream(monkeypatch):
    """Capture outbound requests and answer them from `upstream.respond`."""
    state = {
        'requests': [],
        'respond': lambda req: httpx.Response(
            201, json={'audit': 'ok'}, headers={'x-upstream': '1'}
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state['requests'].append(request)
        return state['respond'](request)

    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(proxy_module.httpx, 'AsyncClient', client_factory)
    return state


@pytest.fixture
def client():
    container = DeprecatedApiContainer(floware_base_url=BASE_URL + '/')
    container.wire(packages=['deprecated_api_module.controllers'])
    common = CommonContainer()
    common.wire(packages=['deprecated_api_module.controllers'])
    app = FastAPI()
    app.include_router(deprecated_api_router, prefix='/floware')
    yield TestClient(app)
    container.unwire()
    common.unwire()


def test_forwards_exact_body_and_headers(client, upstream):
    raw = b'{"image": "data:image/jpeg;base64,AAAA", "metadata": {"loan_id": " x "},  "extra": 1}'
    response = client.post(
        '/floware/v1/image/analyse?trace=1',
        content=raw,
        headers={
            'Authorization': 'Bearer token-123',
            'Content-Type': 'application/json',
            'X-Custom-Header': 'keep-me',
        },
    )

    assert len(upstream['requests']) == 1
    sent = upstream['requests'][0]
    assert sent.method == 'POST'
    assert str(sent.url) == AUDIT_URL + '?trace=1'
    assert sent.content == raw
    assert sent.headers['authorization'] == 'Bearer token-123'
    assert sent.headers['content-type'] == 'application/json'
    assert sent.headers['x-custom-header'] == 'keep-me'
    # Describes the inbound connection, so it is recomputed, not copied.
    assert sent.headers['host'] == 'floware.internal:8001'
    assert sent.headers['content-length'] == str(len(raw))

    assert response.status_code == 201
    assert response.json() == {'audit': 'ok'}


def test_passes_upstream_errors_through(client, upstream):
    upstream['respond'] = lambda req: httpx.Response(422, json={'detail': 'bad'})

    response = client.post('/floware/v1/image/analyse', json={'a': 1})

    assert response.status_code == 422
    assert response.json() == {'detail': 'bad'}


def test_unreachable_upstream_returns_502(client, upstream):
    def fail(req):
        raise httpx.ConnectError('connection refused', request=req)

    upstream['respond'] = fail

    response = client.post('/floware/v1/image/analyse', json={'a': 1})

    assert response.status_code == 502


def test_historical_images_endpoint_is_removed(client, upstream):
    response = client.post('/floware/v1/image/historical_images', json={})

    assert response.status_code in (404, 405)
    assert upstream['requests'] == []
