"""Unit tests for RequireAuthMiddleware helpers and auth validators."""

import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response

from common_module.security.secret_cipher import SecretCipher
from flo_cloud._types import FloCipher
from flo_utils.envelope import EnvelopeCipher

from user_management_module.authorization.require_auth import (
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


class FakeKms(FloCipher):
    def encrypt(self, plaintext):
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        return b'kms:' + bytes(reversed(data))

    def decrypt(self, ciphertext):
        return bytes(reversed(ciphertext[4:]))

    def encrypt_for_storage(self, plaintext):
        raise NotImplementedError

    def decrypt_from_storage(self, stored):
        raise NotImplementedError


def _cipher(enabled: bool) -> SecretCipher:
    return SecretCipher(
        enabled=enabled, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def _signed_hmac_request(secret: str):
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
    return request


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
@pytest.mark.parametrize('enabled', [False, True], ids=['flag_off', 'flag_on'])
async def test_validate_hmac_signature_accepts_valid_header_nonce(enabled):
    secret = 'super-secret'
    cipher = _cipher(enabled)
    stored = cipher.protect(secret)
    assert SecretCipher.is_encrypted(stored) is enabled

    repo = AsyncMock()
    repo.find_one = AsyncMock(return_value=SimpleNamespace(client_secret=stored))

    assert (
        await validate_hmac_signature(_signed_hmac_request(secret), repo, cipher)
        is True
    )


@pytest.mark.asyncio
async def test_validate_hmac_signature_rejects_stored_form_of_the_other_mode():
    secret = 'super-secret'
    repo = AsyncMock()

    # Encrypted secret while encryption is off
    repo.find_one = AsyncMock(
        return_value=SimpleNamespace(client_secret=_cipher(True).protect(secret))
    )
    assert (
        await validate_hmac_signature(
            _signed_hmac_request(secret), repo, _cipher(False)
        )
        is False
    )

    # Plaintext secret while encryption is on
    repo.find_one = AsyncMock(return_value=SimpleNamespace(client_secret=secret))
    assert (
        await validate_hmac_signature(_signed_hmac_request(secret), repo, _cipher(True))
        is False
    )


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

    assert await validate_hmac_signature(request, repo, _cipher(False)) is False
    repo.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_validate_hmac_signature_rejects_missing_headers():
    request = MagicMock()
    request.headers = Headers({})
    request.state = SimpleNamespace(request_id='r1')
    assert await validate_hmac_signature(request, AsyncMock(), _cipher(False)) is False


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


_MTLS_NAMESPACES = ('client-applications', 'gpu-processing')


class TestRequireAuthMiddlewareConfig:
    """Auth settings are constructor arguments, not module or environment state."""

    def test_defaults_are_production_safe(self):
        middleware = RequireAuthMiddleware(
            app=MagicMock(), mtls_allowed_namespaces=_MTLS_NAMESPACES
        )

        assert middleware.app_env == 'production'
        assert middleware.passthrough_secret is None
        assert middleware.required_hmac_apis == ['/floware/v1/image/analyse']
        assert middleware.mtls_allowed_principal_prefixes == mtls_principal_prefixes(
            _MTLS_NAMESPACES
        )

    def test_configured_routes_extend_the_builtin_hmac_route(self):
        middleware = RequireAuthMiddleware(
            app=MagicMock(),
            hmac_routes=['/floware/v1/webhooks/{id}'],
            mtls_allowed_namespaces=_MTLS_NAMESPACES,
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
            app=MagicMock(),
            app_env='dev',
            passthrough_secret='abc',
            mtls_allowed_namespaces=_MTLS_NAMESPACES,
        )
        prod = RequireAuthMiddleware(
            app=MagicMock(), mtls_allowed_namespaces=_MTLS_NAMESPACES
        )

        assert (local.app_env, local.passthrough_secret) == ('dev', 'abc')
        assert (prod.app_env, prod.passthrough_secret) == ('production', None)


def _xfcc_request(xfcc: str):
    request = MagicMock()
    request.headers = Headers({'X-Forwarded-Client-Cert': xfcc})
    request.state = SimpleNamespace()
    return request


@pytest.mark.asyncio
async def test_validate_mtls_auth_uses_the_last_xfcc_entry():
    # The first entry came in as a request header; the sidecar appended the last
    request = _xfcc_request(
        'By=spiffe://cluster.local/ns/floware/sa/floware;'
        'URI=spiffe://cluster.local/ns/evil/sa/forged,'
        'By=spiffe://cluster.local/ns/floware/sa/floware;Hash=abc;'
        'URI=spiffe://cluster.local/ns/client-applications/sa/call-processing'
    )

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is True
    assert request.state.session.user_id == 'service'


@pytest.mark.asyncio
async def test_validate_mtls_auth_ignores_a_spoofed_first_xfcc_entry():
    request = _xfcc_request(
        'URI=spiffe://cluster.local/ns/client-applications/sa/forged,'
        'By=spiffe://cluster.local/ns/floware/sa/floware;'
        'URI=spiffe://cluster.local/ns/evil/sa/real'
    )

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is False
    assert not hasattr(request.state, 'session')


@pytest.mark.asyncio
async def test_validate_mtls_auth_accepts_a_bare_spiffe_header():
    request = _xfcc_request('spiffe://cluster.local/ns/client-applications/sa/app')

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is True
    assert request.state.session.user_id == 'service'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'principal',
    [
        'spiffe://cluster.local/ns/client-applications-evil/sa/app',
        'spiffe://cluster.local/ns/client-applications',
    ],
)
async def test_validate_mtls_auth_requires_a_namespace_boundary(principal):
    request = _xfcc_request(f'URI={principal}')

    assert await validate_mtls_auth(request, CLIENT_APPS_PREFIXES) is False


# ---- secret access ----------------------------------------------------------

_SERVICE_XFCC = 'URI=spiffe://cluster.local/ns/client-applications/sa/app'


def _http_request(path: str = '/floware/v1/llm-inference-configs/x', headers=None):
    return Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': path,
            'query_string': b'',
            'headers': [
                (key.lower().encode(), value.encode())
                for key, value in (headers or {}).items()
            ],
        }
    )


def _jwt_deps():
    token_service = MagicMock()
    token_service.decode_token.return_value = {
        'session_id': 's1',
        'user_id': 'u1',
        'role_id': 'r1',
    }
    cache_manager = MagicMock()
    cache_manager.get_str.return_value = '{"user_id": "u1"}'
    return {'token_service': token_service, 'cache_manager': cache_manager}


async def _secret_access_after_dispatch(middleware, request, **deps):
    """Run the middleware and return request.state.secret_access as the route sees it,
    or None when the request never reaches the route."""
    seen = {}

    async def call_next(req):
        seen['secret_access'] = req.state.secret_access
        return Response('ok')

    formatter = MagicMock()
    formatter.buildErrorResponse.return_value = {'error': 'x'}
    deps = {
        'token_service': MagicMock(),
        'response_formatter': formatter,
        'session_repository': AsyncMock(),
        'cache_manager': MagicMock(),
        'auth_secrets_repository': AsyncMock(),
        'secret_cipher': _cipher(False),
        **deps,
    }
    await middleware.dispatch(request, call_next, **deps)
    return seen.get('secret_access')


def _middleware(app_env='production', passthrough_secret=None):
    return RequireAuthMiddleware(
        app=MagicMock(),
        app_env=app_env,
        passthrough_secret=passthrough_secret,
        mtls_allowed_namespaces=_MTLS_NAMESPACES,
    )


@pytest.mark.asyncio
async def test_secret_access_granted_to_a_valid_mtls_caller():
    request = _http_request(headers={'X-Forwarded-Client-Cert': _SERVICE_XFCC})

    assert await _secret_access_after_dispatch(_middleware(), request) is True
    assert request.state.session.user_id == 'service'


@pytest.mark.asyncio
async def test_secret_access_not_granted_to_a_rejected_mtls_caller():
    request = _http_request(
        headers={
            'X-Forwarded-Client-Cert': (
                'URI=spiffe://cluster.local/ns/client-applications-evil/sa/app'
            )
        }
    )

    assert await _secret_access_after_dispatch(_middleware(), request) is None
    assert request.state.secret_access is False


@pytest.mark.asyncio
async def test_secret_access_granted_to_passthrough_outside_production():
    request = _http_request(headers={RootfloHeaders.PASSTHROUGH: 'shared-secret'})

    assert (
        await _secret_access_after_dispatch(
            _middleware(app_env='dev', passthrough_secret='shared-secret'), request
        )
        is True
    )


@pytest.mark.asyncio
async def test_secret_access_denied_to_passthrough_in_production():
    # The passthrough header is ignored in production; the caller gets in on its
    # JWT, which never grants secret access.
    request = _http_request(
        headers={
            RootfloHeaders.PASSTHROUGH: 'shared-secret',
            'Authorization': 'Bearer token',
        }
    )

    assert (
        await _secret_access_after_dispatch(
            _middleware(passthrough_secret='shared-secret'), request, **_jwt_deps()
        )
        is False
    )
    assert request.state.session.user_id == 'u1'


@pytest.mark.asyncio
async def test_secret_access_denied_to_jwt_callers():
    request = _http_request(headers={'Authorization': 'Bearer token'})

    assert (
        await _secret_access_after_dispatch(_middleware(), request, **_jwt_deps())
        is False
    )


@pytest.mark.asyncio
async def test_secret_access_denied_to_jwt_callers_presenting_xfcc():
    # A token takes the JWT path even when an XFCC header is present
    request = _http_request(
        headers={
            'Authorization': 'Bearer token',
            'X-Forwarded-Client-Cert': _SERVICE_XFCC,
        }
    )

    assert (
        await _secret_access_after_dispatch(_middleware(), request, **_jwt_deps())
        is False
    )


@pytest.mark.asyncio
async def test_secret_access_denied_to_hmac_callers():
    secret = 'super-secret'
    signed = _signed_hmac_request(secret)
    request = _http_request(
        path='/floware/v1/image/analyse', headers=dict(signed.headers)
    )
    repo = AsyncMock()
    repo.find_one = AsyncMock(return_value=SimpleNamespace(client_secret=secret))

    assert (
        await _secret_access_after_dispatch(
            _middleware(), request, auth_secrets_repository=repo
        )
        is False
    )
    assert request.state.session.user_id == 'hmac-service'
