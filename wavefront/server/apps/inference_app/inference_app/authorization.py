"""Inference app authorization.

Every route is open today (callers are services inside the cluster), so the
default provider authenticates no one and allows only PUBLIC actions. A provider
selected with ``AUTHZ_PROVIDER`` can close them.
"""

from __future__ import annotations

from authz_module import AuthzProvider, install, load_provider
from authz_module.default import (
    AnonymousAuthenticator,
    DefaultAuthorizer,
    DenyingResolver,
)
from authz_module.middleware import AuthzMiddleware

PUBLIC_PATHS = ('/docs', '/openapi.json', '/redoc')


def build_provider() -> AuthzProvider:
    default = AuthzProvider(
        authenticator=AnonymousAuthenticator(),
        authorizer=DefaultAuthorizer(DenyingResolver()),
    )
    provider = load_provider(service='inference_app', default=default)
    install(provider)
    return provider


class InferenceAuthMiddleware(AuthzMiddleware):
    def __init__(self, app, *, provider: AuthzProvider | None = None):
        super().__init__(
            app,
            provider=provider or build_provider(),
            public_paths=PUBLIC_PATHS,
            # No route here has ever been authenticated: unknown paths 404.
            authenticate_undeclared=False,
        )
