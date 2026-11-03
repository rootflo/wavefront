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
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.response_formatter import ResponseFormatter
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


def render_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
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
        except jwt.ExpiredSignatureError as exc:
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.error(
                f'ExpiredSignatureError in require_auth middleware: {exc} '
                f'[Request ID: {request_id}]'
            )
            return render_error(status.HTTP_401_UNAUTHORIZED, TOKEN_EXPIRED)


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
