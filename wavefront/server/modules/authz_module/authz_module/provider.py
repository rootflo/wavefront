"""A provider: the authenticator and authorizer a service runs with."""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import HTTPConnection

from authz_module.protocols import Authenticator, Authorizer


@dataclass(frozen=True)
class AuthzProvider:
    authenticator: Authenticator
    authorizer: Authorizer
    name: str = 'default'


_installed: AuthzProvider | None = None


def install(provider: AuthzProvider | None) -> None:
    """Make ``provider`` the process-wide fallback.

    Requests carry the provider of the middleware that served them; this is
    for code that runs outside a request.
    """
    global _installed
    _installed = provider


def installed() -> AuthzProvider | None:
    return _installed


def provider_for(conn: HTTPConnection | None = None) -> AuthzProvider:
    from authz_module.context import _current_provider

    if conn is not None:
        provider = getattr(conn.state, 'authz_provider', None)
        if provider is not None:
            return provider
    provider = _current_provider.get() or _installed
    if provider is None:
        raise RuntimeError(
            'No authorization provider: add the service authorization middleware '
            'or call authz_module.install()'
        )
    return provider
