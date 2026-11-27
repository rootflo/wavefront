"""DefaultAuthorizer evaluates each legacy rule, and nothing else."""

import pytest

from authz_module import (
    ANONYMOUS,
    Legacy,
    RequestContext,
    ResourceRef,
    define_action,
    service_principal,
    user_principal,
)
from authz_module.default import DefaultAuthorizer, DenyingResolver


class Resolver:
    def __init__(self, *, admin=(), manager=(), console=(), scopes=(), flags=()):
        self.admin, self.manager, self.console = set(admin), set(manager), set(console)
        self.scopes, self.flags = set(scopes), set(flags)

    async def is_admin(self, principal):
        return principal.id in self.admin

    async def is_manager(self, principal):
        return principal.id in self.manager

    async def is_console_user(self, principal):
        return principal.id in self.console

    async def has_resource_scope(self, principal, scope):
        return (principal.id, scope) in self.scopes

    def flag_enabled(self, flag):
        return flag in self.flags


ALICE = user_principal('alice', role_id='r-alice')
BOB = user_principal('bob', role_id='r-bob')


async def allowed(rule, principal, resolver, resource=None, name=None):
    action = name or f'test_default:{rule.kind.title().replace("_", "")}Rule'
    define_action(action, legacy=rule)
    decision = await DefaultAuthorizer(resolver).authorize(
        principal, action, resource, RequestContext()
    )
    return decision.allowed


async def test_public_allows_anonymous():
    assert await allowed(Legacy.PUBLIC, ANONYMOUS, DenyingResolver())


async def test_every_other_rule_refuses_anonymous():
    resolver = Resolver(admin={'anonymous'}, manager={'anonymous'})
    for rule in (Legacy.AUTHENTICATED, Legacy.ADMIN, Legacy.MANAGER_OR_ADMIN):
        assert not await allowed(rule, ANONYMOUS, resolver)


async def test_authenticated_allows_any_principal():
    assert await allowed(Legacy.AUTHENTICATED, ALICE, DenyingResolver())
    assert await allowed(
        Legacy.AUTHENTICATED, service_principal('s'), DenyingResolver()
    )


async def test_admin():
    resolver = Resolver(admin={'alice'})
    assert await allowed(Legacy.ADMIN, ALICE, resolver)
    assert not await allowed(Legacy.ADMIN, BOB, resolver)


async def test_manager_or_admin():
    resolver = Resolver(admin={'alice'}, manager={'bob'})
    carol = user_principal('carol')
    assert await allowed(Legacy.MANAGER_OR_ADMIN, ALICE, resolver)
    assert await allowed(Legacy.MANAGER_OR_ADMIN, BOB, resolver)
    assert not await allowed(Legacy.MANAGER_OR_ADMIN, carol, resolver)


async def test_admin_or_flag():
    rule = Legacy.ADMIN_OR_FLAG('open_reads')
    name = 'test_default:AdminOrFlagRule'
    assert not await allowed(rule, BOB, Resolver(), name=name)
    assert await allowed(rule, BOB, Resolver(flags={'open_reads'}), name=name)
    assert await allowed(rule, ALICE, Resolver(admin={'alice'}), name=name)


async def test_console_user():
    assert await allowed(Legacy.CONSOLE_USER, ALICE, Resolver(console={'alice'}))
    assert not await allowed(Legacy.CONSOLE_USER, BOB, Resolver(console={'alice'}))


async def test_resource_scope():
    rule = Legacy.RESOURCE('dashboard')
    name = 'test_default:ResourceRule'
    resolver = Resolver(scopes={('alice', 'dashboard')})
    assert await allowed(rule, ALICE, resolver, name=name)
    assert not await allowed(rule, BOB, resolver, name=name)


async def test_custom_rule_sees_principal_and_resource():
    async def owner_only(principal, resource, ctx, resolver):
        return resource is not None and resource.id == principal.id

    rule = Legacy.CUSTOM('owner_only', owner_only)
    name = 'test_default:CustomRule'
    assert await allowed(rule, ALICE, Resolver(), ResourceRef('user', 'alice'), name)
    assert not await allowed(rule, ALICE, Resolver(), ResourceRef('user', 'bob'), name)


async def test_denial_carries_no_reason_so_the_route_message_is_used():
    define_action('test_default:Denied', legacy=Legacy.ADMIN)
    decision = await DefaultAuthorizer(DenyingResolver()).authorize(
        ALICE, 'test_default:Denied', None, RequestContext()
    )
    assert not decision.allowed
    assert decision.reason is None


async def test_unknown_action_is_an_error():
    with pytest.raises(KeyError):
        await DefaultAuthorizer(DenyingResolver()).authorize(
            ALICE, 'test_default:NeverDeclared', None, RequestContext()
        )


async def test_hooks_are_no_ops():
    authorizer = DefaultAuthorizer(DenyingResolver())
    from authz_module import Capability, DataQuery

    caps = [Capability('tool', 'a'), Capability('datasource', 'b')]
    agent = ResourceRef('agent', 'x')
    assert await authorizer.filter_capabilities(ALICE, agent, caps) == caps
    assert (await authorizer.authorize_call(ALICE, agent, caps[0], None)).allowed
    query = DataQuery(datasource=ResourceRef('datasource', 'd'), operation='query')
    assert await authorizer.before_query(ALICE, query, None) is query
