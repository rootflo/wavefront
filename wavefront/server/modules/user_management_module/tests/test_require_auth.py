"""Unit tests for RequireAuthMiddleware helpers and auth validators."""

import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import Headers

from user_management_module.authorization.require_auth import (
    DEFAULT_MTLS_ALLOWED_NAMESPACES,
    RequireAuthMiddleware,
    is_request_hmac,
    matches_any_route,
    matches_dynamic_route,
    mtls_principal_prefixes,
    optional_auth_apis,
    validate_hmac_signature,
    validate_mtls_auth,
    validate_passthrough_auth,
)
from user_management_module.constants.auth import RootfloHeaders, SERVICE_AUTH_ROLE_ID


def test_matches_dynamic_route_success():
    assert matches_dynamic_route(
        '/floware/v1/triggers/abc/xyz/invoke',
        '/floware/v1/triggers/{trigger_id}/{agentic_id}/invoke',
    )


def test_matches_dynamic_route_rejects_extra_segments():
    assert not matches_dynamic_route(
        '/floware/v1/triggers/abc/xyz/extra/invoke',
        '/floware/v1/triggers/{trigger_id}/{agentic_id}/invoke',
    )


def test_matches_any_route_exact_and_dynamic():
    assert matches_any_route('/floware/v1/health', optional_auth_apis)
    assert matches_any_route(
        '/floware/v1/triggers/t1/a1/invoke',
        optional_auth_apis,
    )
    assert not matches_any_route('/floware/v1/users', optional_auth_apis)


def test_is_request_hmac_true_when_any_hmac_header_present():
    assert is_request_hmac(Headers({RootfloHeaders.CLIENT_KEY: 'k'}))
    assert is_request_hmac(Headers({RootfloHeaders.SIGNATURE: 's'}))
    assert not is_request_hmac(Headers({'Authorization': 'Bearer x'}))


@pytest.mark.asyncio
async def test_validate_hmac_signature_accepts_valid_header_nonce():
    secret = 'super-secret'
    ts = str(int(time.time()))
    nonce = 'n' * 32
    signature = hmac.new(
        secret.encode(), f'{nonce}:{ts}'.encode(), hashlib.sha256
    ).hexdigest()

    request = MagicMock()
    request.headers = Headers(
        {
            RootfloHeaders.CLIENT_KEY: 'client',
            RootfloHeaders.SIGNATURE: signature,
            RootfloHeaders.TIMESTAMP: ts,
            RootfloHeaders.NONCE: nonce,
        }
    )
    request.state = SimpleNamespace(request_id='r1')

    repo = AsyncMock()
    repo.find_one = AsyncMock(return_value=SimpleNamespace(client_secret=secret))

    assert await validate_hmac_signature(request, repo) is True


@pytest.mark.asyncio
async def test_validate_hmac_signature_rejects_stale_timestamp():
    request = MagicMock()
    request.headers = Headers(
        {
            RootfloHeaders.CLIENT_KEY: 'client',
            RootfloHeaders.SIGNATURE: 'sig',
            RootfloHeaders.TIMESTAMP: str(int(time.time()) - 1000),
            RootfloHeaders.NONCE: 'n' * 32,
        }
    )
    request.state = SimpleNamespace(request_id='r1')
    repo = AsyncMock()

    assert await validate_hmac_signature(request, repo) is False
    repo.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_validate_hmac_signature_rejects_missing_headers():
    request = MagicMock()
    request.headers = Headers({})
    request.state = SimpleNamespace(request_id='r1')
    assert await validate_hmac_signature(request, AsyncMock()) is False


CLIENT_APPS_PREFIXES = mtls_principal_prefixes(['client-applications'])


@pytest.mark.asyncio
async def test_validate_mtls_auth_accepts_allowed_spiffe():
    request = MagicMock()
    request.headers = Headers(
        {
            'X-Forwarded-Client-Cert': (
                'URI=spiffe://cluster.local/ns/client-applications/sa/app'
            )
        }
    )
    request.state = SimpleNamespace()

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is True
    assert request.state.session.role_id == SERVICE_AUTH_ROLE_ID


@pytest.mark.asyncio
async def test_validate_mtls_auth_rejects_disallowed_namespace():
    request = MagicMock()
    request.headers = Headers(
        {'X-Forwarded-Client-Cert': 'URI=spiffe://cluster.local/ns/evil/sa/app'}
    )
    request.state = SimpleNamespace()

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is False


def _passthrough_request(header_value):
    request = MagicMock()
    request.headers = Headers({RootfloHeaders.PASSTHROUGH: header_value})
    request.state = SimpleNamespace()
    return request


def test_validate_passthrough_auth_success():
    formatter = MagicMock()

    assert (
        validate_passthrough_auth(
            _passthrough_request('shared-secret'), formatter, 'shared-secret'
        )
        is None
    )


def test_validate_passthrough_auth_sets_service_session():
    request = _passthrough_request('shared-secret')

    validate_passthrough_auth(request, MagicMock(), 'shared-secret')

    assert request.state.session.user_id == 'passthrough'


def test_validate_passthrough_auth_mismatch():
    formatter = MagicMock()
    formatter.buildErrorResponse.return_value = {'error': 'x'}

    response = validate_passthrough_auth(
        _passthrough_request('wrong'), formatter, 'shared-secret'
    )

    assert response is not None
    assert response.status_code == 401


@pytest.mark.parametrize('secret', [None, ''])
def test_validate_passthrough_auth_unconfigured(secret):
    formatter = MagicMock()
    formatter.buildErrorResponse.return_value = {'error': 'x'}

    response = validate_passthrough_auth(
        _passthrough_request('anything'), formatter, secret
    )

    assert response is not None
    assert response.status_code == 500


class TestRequireAuthMiddlewareConfig:
    """Auth settings are constructor arguments, not module or environment state."""

    def test_defaults_are_production_safe(self):
        middleware = RequireAuthMiddleware(app=MagicMock())

        assert middleware.app_env == 'production'
        assert middleware.passthrough_secret is None
        assert middleware.required_hmac_apis == ['/floware/v1/image/analyse']
        assert middleware.mtls_allowed_principal_prefixes == mtls_principal_prefixes(
            DEFAULT_MTLS_ALLOWED_NAMESPACES
        )

    def test_configured_routes_extend_the_builtin_hmac_route(self):
        middleware = RequireAuthMiddleware(
            app=MagicMock(), hmac_routes=['/floware/v1/webhooks/{id}']
        )

        assert middleware.required_hmac_apis == [
            '/floware/v1/image/analyse',
            '/floware/v1/webhooks/{id}',
        ]

    def test_namespaces_become_spiffe_prefixes(self):
        middleware = RequireAuthMiddleware(
            app=MagicMock(), mtls_allowed_namespaces=['team-a']
        )

        assert middleware.mtls_allowed_principal_prefixes == (
            'spiffe://cluster.local/ns/team-a',
        )

    def test_instances_do_not_share_settings(self):
        local = RequireAuthMiddleware(
            app=MagicMock(), app_env='dev', passthrough_secret='abc'
        )
        prod = RequireAuthMiddleware(app=MagicMock())

        assert (local.app_env, local.passthrough_secret) == ('dev', 'abc')
        assert (prod.app_env, prod.passthrough_secret) == ('production', None)
