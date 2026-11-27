"""The interfaces a provider implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from starlette.requests import HTTPConnection

from authz_module.context import RequestContext
from authz_module.principal import Principal
from authz_module.resource import ResourceRef


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None
    #: HTTP status for a denial. None lets the route's own default apply.
    status_code: int | None = None

    @classmethod
    def allow(cls, reason: str | None = None) -> 'Decision':
        return cls(True, reason)

    @classmethod
    def deny(cls, reason: str | None = None, status_code: int | None = None):
        return cls(False, reason, status_code)

    def __bool__(self) -> bool:
        return self.allowed


class AuthenticationError(Exception):
    """The caller presented credentials and they did not check out."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AccessDenied(Exception):
    """Raised by hooks (and ``ensure_allowed``) to refuse an operation."""

    def __init__(self, decision: Decision, action: str | None = None):
        super().__init__(decision.reason or 'Access denied')
        self.decision = decision
        self.action = action


@dataclass(frozen=True)
class Capability:
    """Something an agent can use: a tool, a datasource, a knowledge base."""

    kind: str
    name: str
    attributes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class DataQuery:
    """A query about to run against a datasource.

    ``before_query`` may return a different query (a narrower one, say) or raise
    ``AccessDenied``.
    """

    datasource: ResourceRef
    operation: str
    resource: str | None = None
    text: str | None = None
    filter: str | None = None
    params: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class DecisionEvent:
    principal: Principal
    action: str
    resource: ResourceRef | None
    decision: Decision
    ctx: RequestContext
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class Authenticator(Protocol):
    async def authenticate(self, conn: HTTPConnection) -> Principal | None:
        """The caller's principal, or None when no credentials were presented.

        Raise ``AuthenticationError`` for credentials that fail to verify.
        """
        ...


@runtime_checkable
class Authorizer(Protocol):
    async def authorize(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef | None,
        ctx: RequestContext,
    ) -> Decision: ...

    async def filter_capabilities(
        self,
        principal: Principal,
        agent: ResourceRef,
        capabilities: Sequence[Capability],
    ) -> list[Capability]: ...

    async def authorize_call(
        self,
        principal: Principal,
        agent: ResourceRef,
        capability: Capability,
        ctx: RequestContext,
    ) -> Decision: ...

    async def before_query(
        self, principal: Principal, query: DataQuery, ctx: RequestContext
    ) -> DataQuery: ...

    async def record(self, event: DecisionEvent) -> None: ...


class BaseAuthorizer:
    """Hook defaults: allow everything, change nothing, record nothing."""

    async def authorize(self, principal, action, resource, ctx) -> Decision:
        raise NotImplementedError

    async def filter_capabilities(self, principal, agent, capabilities):
        return list(capabilities)

    async def authorize_call(self, principal, agent, capability, ctx) -> Decision:
        return Decision.allow()

    async def before_query(self, principal, query, ctx) -> DataQuery:
        return query

    async def record(self, event: DecisionEvent) -> None:
        return None
