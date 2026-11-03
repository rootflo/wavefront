"""Test doubles for providers and principals."""

from __future__ import annotations

from typing import Callable, Iterable

from starlette.requests import HTTPConnection

from authz_module.context import RequestContext
from authz_module.principal import (
    ANONYMOUS,
    Principal,
    service_principal,
    user_principal,
)
from authz_module.protocols import BaseAuthorizer, Decision
from authz_module.provider import AuthzProvider
from authz_module.resource import ResourceRef

__all__ = [
    'ANONYMOUS',
    'AllowAll',
    'DenyAll',
    'ScriptedAuthorizer',
    'StaticAuthenticator',
    'make_provider',
    'service_principal',
    'user_principal',
]


class AllowAll(BaseAuthorizer):
    async def authorize(self, principal, action, resource, ctx) -> Decision:
        return Decision.allow()


class DenyAll(BaseAuthorizer):
    async def authorize(self, principal, action, resource, ctx) -> Decision:
        return Decision.deny('denied by DenyAll')


Rule = Callable[[Principal, str, ResourceRef | None], bool | None]


class ScriptedAuthorizer(BaseAuthorizer):
    """Allow exactly what a test says, and remember what it was asked.

    ``allow`` is a set of action names (``'*'`` for all) or a function
    ``(principal, action, resource) -> bool``.
    """

    def __init__(self, allow: Iterable[str] | Rule = ()):
        self._rule = allow if callable(allow) else None
        self._allowed = frozenset(()) if callable(allow) else frozenset(allow)
        self.calls: list[tuple[Principal, str, ResourceRef | None]] = []

    async def authorize(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef | None,
        ctx: RequestContext,
    ) -> Decision:
        self.calls.append((principal, action, resource))
        if self._rule is not None:
            allowed = bool(self._rule(principal, action, resource))
        else:
            allowed = '*' in self._allowed or action in self._allowed
        # No reason, so a route's own denial message shows, as with the default.
        return Decision(allowed)

    @property
    def actions(self) -> list[str]:
        return [action for _, action, _ in self.calls]


class StaticAuthenticator:
    """Authenticate every request as one principal (None: no credentials)."""

    def __init__(self, principal: Principal | None):
        self.principal = principal

    async def authenticate(self, conn: HTTPConnection) -> Principal | None:
        return self.principal


def make_provider(
    principal: Principal | None = None,
    authorizer: BaseAuthorizer | None = None,
) -> AuthzProvider:
    return AuthzProvider(
        authenticator=StaticAuthenticator(principal),
        authorizer=authorizer or AllowAll(),
        name='testing',
    )
