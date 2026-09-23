"""Unit tests for RequireAuthMiddleware helpers and auth validators."""

import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import Headers

from user_management_module.authorization.require_auth import (
    is_request_hmac,
    matches_any_route,
    matches_dynamic_route,
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


@pytest.mark.asyncio
async def test_validate_mtls_auth_accepts_allowed_spiffe(monkeypatch):
    monkeypatch.setattr(
        'user_management_module.authorization.require_auth.mtls_allowed_principal_prefixes',
        ('spiffe://cluster.local/ns/client-applications',),
    )
    request = MagicMock()
    request.headers = Headers(
        {
            'X-Forwarded-Client-Cert': (
                'URI=spiffe://cluster.local/ns/client-applications/sa/app'
            )
        }
    )
    request.state = SimpleNamespace()

    assert await validate_mtls_auth(request) is True
    assert request.state.session.role_id == SERVICE_AUTH_ROLE_ID


@pytest.mark.asyncio
async def test_validate_mtls_auth_rejects_disallowed_namespace(monkeypatch):
    monkeypatch.setattr(
        'user_management_module.authorization.require_auth.mtls_allowed_principal_prefixes',
        ('spiffe://cluster.local/ns/client-applications',),
    )
    request = MagicMock()
    request.headers = Headers(
        {'X-Forwarded-Client-Cert': 'URI=spiffe://cluster.local/ns/evil/sa/app'}
    )
    request.state = SimpleNamespace()

    assert await validate_mtls_auth(request) is False


def test_validate_passthrough_auth_success(monkeypatch):
    monkeypatch.setattr(
        'user_management_module.authorization.require_auth.passthrough_secret',
        'shared-secret',
    )
    request = MagicMock()
    request.headers = Headers({RootfloHeaders.PASSTHROUGH: 'shared-secret'})
    request.state = SimpleNamespace()
    formatter = MagicMock()

    assert validate_passthrough_auth(request, formatter) is None
    assert request.state.session.user_id == 'passthrough'


def test_validate_passthrough_auth_mismatch(monkeypatch):
    monkeypatch.setattr(
        'user_management_module.authorization.require_auth.passthrough_secret',
        'shared-secret',
    )
    request = MagicMock()
    request.headers = Headers({RootfloHeaders.PASSTHROUGH: 'wrong'})
    request.state = SimpleNamespace()
    formatter = MagicMock()
    formatter.buildErrorResponse.return_value = {'error': 'x'}

    response = validate_passthrough_auth(request, formatter)
    assert response is not None
    assert response.status_code == 401


def test_validate_passthrough_auth_unconfigured(monkeypatch):
    monkeypatch.setattr(
        'user_management_module.authorization.require_auth.passthrough_secret',
        None,
    )
    request = MagicMock()
    request.headers = Headers({RootfloHeaders.PASSTHROUGH: 'anything'})
    request.state = SimpleNamespace()
    formatter = MagicMock()
    formatter.buildErrorResponse.return_value = {'error': 'x'}

    response = validate_passthrough_auth(request, formatter)
    assert response is not None
    assert response.status_code == 500
