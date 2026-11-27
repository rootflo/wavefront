"""Call processing's request authentication and authorization.

Callers are other services. In production the service mesh (mTLS) is the
authentication, so every caller that reaches a non-public route is accepted as
a service; elsewhere it must present the passthrough secret.
"""

from __future__ import annotations

from authz_module import (
    AuthenticationError,
    AuthzProvider,
    Principal,
    install,
    load_provider,
    service_principal,
)
from authz_module.default import DefaultAuthorizer, DenyingResolver
from authz_module.middleware import AuthzMiddleware
from common_module.log.logger import logger
from fastapi import status
from starlette.requests import HTTPConnection

PASSTHROUGH_HEADER = 'X-Passthrough'
PUBLIC_PATHS = ('/docs', '/openapi.json', '/redoc')


class CallProcessingAuthenticator:
    def __init__(self, *, app_env: str | None, passthrough_secret: str | None):
        self.app_env = app_env or 'production'
        self.passthrough_secret = passthrough_secret or None

    async def authenticate(self, conn: HTTPConnection) -> Principal:
        if self.app_env == 'production':
            return service_principal('service-mesh')

        if not self.passthrough_secret:
            logger.warning('Passthrough not configured')
            raise AuthenticationError(
                'Passthrough not configured', status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        passthrough = conn.headers.get(PASSTHROUGH_HEADER)
        if not passthrough:
            logger.warning('Missing X-Passthrough header')
            raise AuthenticationError('Missing X-Passthrough header')

        if passthrough != self.passthrough_secret:
            logger.warning('Invalid X-Passthrough header')
            raise AuthenticationError('Invalid authentication credentials')

        return service_principal('passthrough')


def build_provider(*, app_env: str | None, passthrough_secret: str | None):
    default = AuthzProvider(
        authenticator=CallProcessingAuthenticator(
            app_env=app_env, passthrough_secret=passthrough_secret
        ),
        # No roles here: only PUBLIC and AUTHENTICATED rules are in use.
        authorizer=DefaultAuthorizer(DenyingResolver()),
    )
    provider = load_provider(service='call_processing', default=default)
    # Websocket routes are authorized by their dependency, outside the middleware.
    install(provider)
    return provider


class CallProcessingAuthMiddleware(AuthzMiddleware):
    def __init__(self, app, *, provider: AuthzProvider):
        super().__init__(
            app,
            provider=provider,
            public_paths=PUBLIC_PATHS,
            authenticate_undeclared=False,
        )
