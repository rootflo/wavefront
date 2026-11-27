"""Floware's request authentication and authorization middleware.

Authentication is ``FlowareAuthenticator``; authorization is whatever the route
declares with ``requires``/``public_route``, decided by the provider that
``AUTHZ_PROVIDER`` selects (by default: each action's legacy rule).
"""

from __future__ import annotations

from collections.abc import Sequence

import jwt
from authz_module import AuthzProvider, install, load_provider
from authz_module.default import DefaultAuthorizer
from authz_module.middleware import AuthzMiddleware
from common_module.blocking_io import BlockingPoolBusyError, retry_after_seconds
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.response_formatter import ResponseFormatter
from common_module.security.public_key_cache import PublicKeyUnavailableError
from fastapi import status
from fastapi.responses import JSONResponse
from starlette.requests import Request

from user_management_module.authorization.authenticator import (
    BASE_HMAC_APIS,
    TOKEN_EXPIRED,
    FlowareAuthenticator,
    is_request_hmac,
    matches_any_route,
    matches_dynamic_route,
    mtls_principal_prefixes,
    validate_hmac_signature,
    validate_mtls_auth,
    validate_passthrough_auth,
)
from user_management_module.authorization.legacy_resolver import (
    FlowareLegacyResolver,
)

# Framework routes that cannot declare anything themselves.
PUBLIC_PATHS = ('/', '/docs', '/openapi.json')


def render_error(
    status_code: int, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=ResponseFormatter().buildErrorResponse(error=message),
    )


def default_provider(authenticator: FlowareAuthenticator) -> AuthzProvider:
    return AuthzProvider(
        authenticator=authenticator,
        authorizer=DefaultAuthorizer(FlowareLegacyResolver()),
    )


class RequireAuthMiddleware(AuthzMiddleware):
    def __init__(
        self,
        app,
        *,
        app_env: str = 'production',
        passthrough_secret: str | None = None,
        hmac_routes: Sequence[str] = (),
        mtls_allowed_namespaces: Sequence[str],
        provider: AuthzProvider | None = None,
    ):
        """
        Args:
            app_env: Passthrough auth is only honoured when this is not
                ``production``.
            passthrough_secret: Shared secret for passthrough auth (local use);
                optional.
            hmac_routes: Extra routes authenticated by HMAC signature.
            mtls_allowed_namespaces: Namespaces whose SPIFFE identities are
                accepted for mTLS auth.
            provider: Use this provider instead of the one ``AUTHZ_PROVIDER``
                selects.
        """
        self.authenticator = FlowareAuthenticator(
            app_env=app_env,
            passthrough_secret=passthrough_secret,
            hmac_routes=hmac_routes,
            mtls_allowed_namespaces=mtls_allowed_namespaces,
        )
        if provider is None:
            provider = load_provider(
                service='floware', default=default_provider(self.authenticator)
            )
        install(provider)
        super().__init__(
            app,
            provider=provider,
            render_error=render_error,
            public_paths=PUBLIC_PATHS,
        )

    @property
    def app_env(self) -> str:
        return self.authenticator.app_env

    @property
    def passthrough_secret(self) -> str | None:
        return self.authenticator.passthrough_secret

    @property
    def required_hmac_apis(self) -> list[str]:
        return self.authenticator.required_hmac_apis

    @property
    def mtls_allowed_principal_prefixes(self) -> tuple[str, ...]:
        return self.authenticator.mtls_allowed_principal_prefixes

    async def dispatch(self, request: Request, call_next):
        # An expired token surfacing from inside a handler has always been
        # answered as an expired session, not a server error.
        try:
            return await super().dispatch(request, call_next)
        except BlockingPoolBusyError as exc:
            # Middleware errors skip the app's exception handlers, so answer here.
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(
                f'Auth busy on {request.method} {request.url.path!r}: {exc} '
                f'[Request ID: {request_id}]'
            )
            return render_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                'The server is busy. Please try again shortly.',
                headers={'Retry-After': str(retry_after_seconds())},
            )
        except PublicKeyUnavailableError as exc:
            # KMS is down: the token may be valid, so 503 (retry), never 401,
            # which clients treat as "logged out".
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.error(
                f'Token key unavailable on {request.method} {request.url.path!r}: '
                f'{exc} [Request ID: {request_id}]'
            )
            return render_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                'Authentication is temporarily unavailable. Please try again shortly.',
                headers={'Retry-After': str(retry_after_seconds())},
            )
        except jwt.ExpiredSignatureError as exc:
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.error(
                f'ExpiredSignatureError in require_auth middleware: {exc} '
                f'[Request ID: {request_id}]'
            )
            return render_error(status.HTTP_401_UNAUTHORIZED, TOKEN_EXPIRED)
        except jwt.InvalidTokenError as exc:
            # Malformed token, wrong algorithm, issuer or audience: the caller's
            # mistake, so 401 and a warning, never a 500.
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(
                f'Invalid token in require_auth middleware: {type(exc).__name__} '
                f'[Request ID: {request_id}]'
            )
            return render_error(status.HTTP_401_UNAUTHORIZED, 'Invalid token')


__all__ = [
    'BASE_HMAC_APIS',
    'PUBLIC_PATHS',
    'RequireAuthMiddleware',
    'default_provider',
    'is_request_hmac',
    'matches_any_route',
    'matches_dynamic_route',
    'mtls_principal_prefixes',
    'render_error',
    'validate_hmac_signature',
    'validate_mtls_auth',
    'validate_passthrough_auth',
]
