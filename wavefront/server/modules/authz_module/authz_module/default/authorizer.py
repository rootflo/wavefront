"""The default authorizer: evaluate each action's legacy rule, nothing more."""

from __future__ import annotations

from typing import Protocol

from authz_module.actions import get_action
from authz_module.context import RequestContext
from authz_module.legacy import LegacyRule
from authz_module.principal import Principal
from authz_module.protocols import BaseAuthorizer, Decision
from authz_module.resource import ResourceRef


class LegacyResolver(Protocol):
    """How a service answers the questions legacy rules ask.

    Each service implements this over its own role data. A question a service
    has no answer for returns False, so a rule it cannot evaluate denies.
    """

    async def is_admin(self, principal: Principal) -> bool: ...

    async def is_manager(self, principal: Principal) -> bool: ...

    async def is_console_user(self, principal: Principal) -> bool: ...

    async def has_resource_scope(self, principal: Principal, scope: str) -> bool: ...

    def flag_enabled(self, flag: str) -> bool: ...


class DenyingResolver:
    """A resolver that answers no to everything."""

    async def is_admin(self, principal):
        return False

    async def is_manager(self, principal):
        return False

    async def is_console_user(self, principal):
        return False

    async def has_resource_scope(self, principal, scope):
        return False

    def flag_enabled(self, flag):
        return False


class DefaultAuthorizer(BaseAuthorizer):
    def __init__(self, resolver: LegacyResolver):
        self.resolver = resolver

    async def authorize(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef | None,
        ctx: RequestContext,
    ) -> Decision:
        rule = get_action(action).legacy
        allowed = await self.evaluate(rule, principal, resource, ctx)
        # No reason on a denial: the route's own message (the one its inline
        # check used to return) is what callers have always seen.
        return Decision(allowed)

    async def evaluate(
        self,
        rule: LegacyRule,
        principal: Principal,
        resource: ResourceRef | None,
        ctx: RequestContext,
    ) -> bool:
        kind = rule.kind
        if kind == 'public':
            return True
        if principal.is_anonymous:
            return False
        if kind == 'authenticated':
            return True
        if kind == 'admin':
            return await self.resolver.is_admin(principal)
        if kind == 'manager_or_admin':
            return await self.resolver.is_admin(
                principal
            ) or await self.resolver.is_manager(principal)
        if kind == 'admin_or_flag':
            return self.resolver.flag_enabled(
                rule.arg or ''
            ) or await self.resolver.is_admin(principal)
        if kind == 'console_user':
            return await self.resolver.is_console_user(principal)
        if kind == 'resource':
            return await self.resolver.has_resource_scope(principal, rule.arg or '')
        if kind == 'custom' and rule.check is not None:
            return bool(await rule.check(principal, resource, ctx, self.resolver))
        return False
