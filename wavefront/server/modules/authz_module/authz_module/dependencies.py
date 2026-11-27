"""Route declarations: ``requires`` and ``public_route``.

Both are FastAPI dependencies that also carry their declaration as metadata
(``__authz__``). The middleware reads that metadata to authorize a request
before the handler runs -- ahead of body parsing and validation, the same point
the old middleware checks ran at. The dependency then only hands the handler
its principal. When no middleware has run (a websocket, or an app built without
it) the dependency enforces the declaration itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, WebSocketException, status
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket

from authz_module.actions import ActionSpec, define_action, get_action
from authz_module.context import RequestContext, _current_principal
from authz_module.legacy import LegacyRule
from authz_module.principal import ANONYMOUS, Principal
from authz_module.protocols import (
    AccessDenied,
    AuthenticationError,
    Decision,
    DecisionEvent,
)
from authz_module.provider import provider_for
from authz_module.resource import ResourceRef, ResourceResolver, resource_type_of

MISSING_CREDENTIALS = 'Token missing in request'


@dataclass(frozen=True)
class RouteAuthz:
    """What one route declares."""

    action: ActionSpec | None = None
    resource: ResourceResolver | ResourceRef | None = field(default=None, compare=False)
    public: bool = False
    deny_status: int = status.HTTP_403_FORBIDDEN
    deny_message: str | None = None

    @property
    def skips_authentication(self) -> bool:
        return self.public or (self.action is not None and self.action.legacy.is_public)

    def resolve_resource(self, conn: HTTPConnection) -> ResourceRef | None:
        if self.resource is None or isinstance(self.resource, ResourceRef):
            return self.resource
        return self.resource(conn)


def requires(
    action: str,
    *,
    legacy: LegacyRule,
    resource: ResourceResolver | ResourceRef | None = None,
    description: str = '',
    deny_status: int = status.HTTP_403_FORBIDDEN,
    deny_message: str | None = None,
):
    """Declare that a route performs ``action``.

    ``legacy`` is the check the route had before this layer; the default
    authorizer evaluates it. ``deny_status`` and ``deny_message`` reproduce the
    response that check gave on a denial.
    """
    spec = define_action(
        action,
        legacy=legacy,
        resource_type=resource_type_of(resource),
        description=description,
    )
    declaration = RouteAuthz(
        action=spec,
        resource=resource,
        deny_status=deny_status,
        deny_message=deny_message,
    )

    async def authorize_route(conn: HTTPConnection) -> Principal:
        return await _enforce(conn, declaration)

    authorize_route.__authz__ = declaration  # type: ignore[attr-defined]
    authorize_route.__name__ = f'requires[{action}]'
    return authorize_route


async def public_route() -> None:
    """Declare a route public: it is neither authenticated nor authorized."""
    return None


public_route.__authz__ = RouteAuthz(public=True)  # type: ignore[attr-defined]


def principal_of(conn: HTTPConnection | None = None) -> Principal:
    from authz_module.context import current_principal

    if conn is not None:
        principal = getattr(conn.state, 'principal', None)
        if principal is not None:
            return principal
    return current_principal() or ANONYMOUS


async def current_principal_dependency(conn: HTTPConnection) -> Principal:
    return principal_of(conn)


async def decide(
    principal: Principal,
    action: str,
    resource: ResourceRef | None = None,
    *,
    conn: HTTPConnection | None = None,
    ctx: RequestContext | None = None,
) -> Decision:
    """Ask the provider, and record the decision."""
    get_action(action)  # unknown actions are a programming error
    provider = provider_for(conn)
    if ctx is None:
        ctx = RequestContext.from_connection(conn) if conn else RequestContext()
    decision = await provider.authorizer.authorize(principal, action, resource, ctx)
    await provider.authorizer.record(
        DecisionEvent(
            principal=principal,
            action=action,
            resource=resource,
            decision=decision,
            ctx=ctx,
        )
    )
    return decision


async def is_allowed(
    conn: HTTPConnection, action: str, resource: ResourceRef | None = None
) -> bool:
    """Whether the request's principal may perform ``action``.

    For checks inside a handler, where the answer shapes the response rather
    than gating the whole route.
    """
    return (await decide(principal_of(conn), action, resource, conn=conn)).allowed


async def ensure_allowed(
    conn: HTTPConnection, action: str, resource: ResourceRef | None = None
) -> None:
    decision = await decide(principal_of(conn), action, resource, conn=conn)
    if not decision.allowed:
        raise AccessDenied(decision, action)


async def _enforce(conn: HTTPConnection, declaration: RouteAuthz) -> Principal:
    if getattr(conn.state, 'authz_enforced', False):
        return principal_of(conn)

    principal = getattr(conn.state, 'principal', None)
    if principal is None:
        if declaration.skips_authentication:
            principal = ANONYMOUS
        else:
            try:
                principal = await provider_for(conn).authenticator.authenticate(conn)
            except AuthenticationError as exc:
                _refuse(conn, exc.status_code, exc.message)
            if principal is None:
                _refuse(conn, status.HTTP_401_UNAUTHORIZED, MISSING_CREDENTIALS)
        conn.state.principal = principal
        # No middleware set the context for this request; this task is the
        # request's own, so the value goes with it.
        _current_principal.set(principal)

    if declaration.action is not None:
        decision = await decide(
            principal,
            declaration.action.name,
            declaration.resolve_resource(conn),
            conn=conn,
        )
        if not decision.allowed:
            _refuse(
                conn,
                decision.status_code or declaration.deny_status,
                decision.reason or declaration.deny_message or 'Forbidden',
            )
    return principal


def _refuse(conn: HTTPConnection, status_code: int, message: str):
    if isinstance(conn, WebSocket):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=message)
    raise HTTPException(status_code=status_code, detail=message)
