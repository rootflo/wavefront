"""Per-request context passed to the authorizer."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

from starlette.requests import HTTPConnection

if TYPE_CHECKING:
    from authz_module.principal import Principal
    from authz_module.provider import AuthzProvider


@dataclass(frozen=True)
class RequestContext:
    ip: str | None = None
    request_id: str | None = None
    method: str | None = None
    path: str | None = None
    mfa: bool = False
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_connection(cls, conn: HTTPConnection) -> 'RequestContext':
        request_id = getattr(conn.state, 'request_id', None)
        return cls(
            ip=conn.client.host if conn.client else None,
            request_id=request_id,
            method=conn.scope.get('method'),
            path=conn.url.path,
        )


_current_principal: ContextVar['Principal | None'] = ContextVar(
    'authz_current_principal', default=None
)
_current_provider: ContextVar['AuthzProvider | None'] = ContextVar(
    'authz_current_provider', default=None
)


def current_principal() -> 'Principal | None':
    """The principal of the request being served, if any.

    For code with no request in hand. Work that outlives the request (a
    background job) must be handed the principal explicitly instead.
    """
    return _current_principal.get()


def set_current(principal: 'Principal | None', provider: 'AuthzProvider | None'):
    return _current_principal.set(principal), _current_provider.set(provider)


def reset_current(tokens) -> None:
    principal_token, provider_token = tokens
    _current_principal.reset(principal_token)
    _current_provider.reset(provider_token)
