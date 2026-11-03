"""Legacy rules: each service's built-in access checks, as data.

Every action records the check that guarded it before this layer existed. The
default authorizer evaluates exactly that rule, so moving a check from inline
code onto an action does not change who may call it. Other providers ignore
the rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from authz_module.context import RequestContext
    from authz_module.principal import Principal
    from authz_module.resource import ResourceRef

    CustomCheck = Callable[
        [Principal, ResourceRef | None, RequestContext, Any], Awaitable[bool]
    ]


@dataclass(frozen=True)
class LegacyRule:
    kind: str
    arg: str | None = None
    # Not part of equality: two declarations of one custom rule compare equal.
    check: Any = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        name = self.kind.upper()
        return name if self.arg is None else f'{name}({self.arg})'

    @property
    def is_public(self) -> bool:
        return self.kind == 'public'


class Legacy:
    """The legacy rules a route can carry."""

    #: Anyone, signed in or not. The route is not authenticated.
    PUBLIC = LegacyRule('public')
    #: Any authenticated caller.
    AUTHENTICATED = LegacyRule('authenticated')
    #: The admin role. Service identities count as admins.
    ADMIN = LegacyRule('admin')
    #: The manager or admin role.
    MANAGER_OR_ADMIN = LegacyRule('manager_or_admin')
    #: A console user.
    CONSOLE_USER = LegacyRule('console_user')

    @staticmethod
    def ADMIN_OR_FLAG(flag: str) -> LegacyRule:
        """Admin, or any authenticated caller while deployment flag ``flag`` is on."""
        return LegacyRule('admin_or_flag', flag)

    @staticmethod
    def RESOURCE(scope: str) -> LegacyRule:
        """A role granted a resource of ``scope``."""
        return LegacyRule('resource', scope)

    @staticmethod
    def CUSTOM(name: str, check: 'CustomCheck') -> LegacyRule:
        """A check that fits none of the above.

        ``check(principal, resource, ctx, resolver)`` returns whether to allow.
        Every custom rule is listed in the catalog by ``name`` and needs review.
        """
        return LegacyRule('custom', name, check)
