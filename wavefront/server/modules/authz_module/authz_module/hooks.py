"""Runtime hooks, for code paths that are not a single route.

Call sites use these functions rather than the authorizer directly, so a
service with no provider installed (a script, a test) runs them as no-ops.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

from authz_module.context import RequestContext, current_principal
from authz_module.principal import ANONYMOUS, Principal
from authz_module.protocols import (
    AccessDenied,
    Capability,
    DataQuery,
    Decision,
    DecisionEvent,
)
from authz_module.provider import AuthzProvider, provider_for
from authz_module.resource import ResourceRef

T = TypeVar('T')


def _provider() -> AuthzProvider | None:
    try:
        return provider_for(None)
    except RuntimeError:
        return None


def _principal(principal: Principal | None) -> Principal:
    return principal or current_principal() or ANONYMOUS


async def filter_capabilities(
    agent: ResourceRef,
    items: Sequence[T],
    describe,
    *,
    principal: Principal | None = None,
) -> list[T]:
    """The subset of an agent's ``items`` (tools, say) the principal may use.

    ``describe(item) -> Capability`` names each item for the authorizer.
    """
    provider = _provider()
    if provider is None or not items:
        return list(items)
    described = [(item, describe(item)) for item in items]
    allowed = await provider.authorizer.filter_capabilities(
        _principal(principal), agent, [cap for _, cap in described]
    )
    keep = {(cap.kind, cap.name) for cap in allowed}
    return [item for item, cap in described if (cap.kind, cap.name) in keep]


async def authorize_call(
    agent: ResourceRef,
    capability: Capability,
    *,
    principal: Principal | None = None,
    ctx: RequestContext | None = None,
) -> Decision:
    """Whether an agent may use one capability now. Raise nothing; return."""
    provider = _provider()
    if provider is None:
        return Decision.allow()
    return await provider.authorizer.authorize_call(
        _principal(principal), agent, capability, ctx or RequestContext()
    )


async def ensure_call_allowed(
    agent: ResourceRef,
    capability: Capability,
    *,
    principal: Principal | None = None,
    ctx: RequestContext | None = None,
) -> None:
    decision = await authorize_call(agent, capability, principal=principal, ctx=ctx)
    if not decision.allowed:
        raise AccessDenied(decision, f'{capability.kind}:{capability.name}')


async def before_query(
    query: DataQuery,
    *,
    principal: Principal | None = None,
    ctx: RequestContext | None = None,
) -> DataQuery:
    """The query to actually run. The provider may narrow it or raise AccessDenied."""
    provider = _provider()
    if provider is None:
        return query
    return await provider.authorizer.before_query(
        _principal(principal), query, ctx or RequestContext()
    )


async def record(event: DecisionEvent) -> None:
    provider = _provider()
    if provider is not None:
        await provider.authorizer.record(event)
