"""lint-routes / export-catalog, provider loading, and the runtime hooks."""

import json
import sys
import types

import pytest
from fastapi import APIRouter, Depends, FastAPI

from authz_module import (
    AccessDenied,
    AuthzProvider,
    Capability,
    DataQuery,
    Decision,
    Legacy,
    ResourceRef,
    install,
    public_route,
    requires,
    user_principal,
)
from authz_module import hooks
from authz_module.cli import collect, lint, main
from authz_module.loader import ProviderNotFound, load_provider
from authz_module.testing import AllowAll, StaticAuthenticator, make_provider


def _fixture_app():
    router = APIRouter(
        dependencies=[Depends(requires('test_cli:UseRouter', legacy=Legacy.ADMIN))]
    )

    @router.get('/declared')
    async def declared():
        return {}

    open_router = APIRouter()

    @open_router.get('/health', dependencies=[Depends(public_route)])
    async def health():
        return {}

    @open_router.get('/forgotten')
    async def forgotten():
        return {}

    @open_router.get(
        '/confused',
        dependencies=[
            Depends(public_route),
            Depends(requires('test_cli:Confused', legacy=Legacy.AUTHENTICATED)),
        ],
    )
    async def confused():
        return {}

    app = FastAPI()
    app.include_router(router, prefix='/a')
    app.include_router(open_router, prefix='/b')
    return app


fixture_module = types.ModuleType('authz_cli_fixture')
fixture_module.build_app = _fixture_app
sys.modules['authz_cli_fixture'] = fixture_module


def test_router_level_declarations_count():
    entries = {e.path: e for e in collect(_fixture_app())}
    assert [s.name for s in entries['/a/declared'].actions] == ['test_cli:UseRouter']
    assert entries['/b/health'].public


def test_lint_finds_unannotated_and_contradictory_routes():
    problems = lint(collect(_fixture_app()))
    assert len(problems) == 2
    assert any('/b/forgotten' in p and 'neither' in p for p in problems)
    assert any('/b/confused' in p and 'both' in p for p in problems)


def test_lint_routes_exit_code(capsys):
    assert main(['lint-routes', 'authz_cli_fixture:build_app']) == 1
    assert '2 route(s) not annotated' in capsys.readouterr().err


def test_export_catalog(capsys):
    assert main(['export-catalog', 'authz_cli_fixture:build_app']) == 0
    data = json.loads(capsys.readouterr().out)
    actions = {a['action']: a for a in data['actions']}
    assert actions['test_cli:UseRouter']['legacy'] == 'ADMIN'
    routes = {r['path']: r for r in data['routes']}
    assert routes['/a/declared']['actions'] == ['test_cli:UseRouter']


def test_snapshot_includes_the_access_matrix(capsys):
    assert main(['snapshot', 'authz_cli_fixture:build_app']) == 0
    data = json.loads(capsys.readouterr().out)
    declared = data['access']['GET /a/declared']['status']
    assert declared['anonymous'] == 401
    assert declared['user'] == 403
    assert declared['admin'] == 200
    assert data['access']['GET /b/health']['status']['anonymous'] == 200
    assert len(data['unannotated']) == 2


# --- loader ------------------------------------------------------------------


DEFAULT = make_provider()


def test_default_provider(monkeypatch):
    monkeypatch.delenv('AUTHZ_PROVIDER', raising=False)
    assert load_provider(service='svc', default=DEFAULT) is DEFAULT


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setenv('AUTHZ_PROVIDER', 'does-not-exist')
    with pytest.raises(ProviderNotFound):
        load_provider(service='svc', default=DEFAULT)


def test_entry_point_factory_gets_service_and_default(monkeypatch):
    seen = {}

    def factory(*, service, default):
        seen.update(service=service, default=default)
        return AuthzProvider(default.authenticator, AllowAll(), name='custom')

    class EntryPoint:
        name = 'custom'

        def load(self):
            return factory

    monkeypatch.setattr(
        'authz_module.loader.entry_points', lambda group: [EntryPoint()]
    )
    provider = load_provider(service='floware', default=DEFAULT, name='custom')
    assert provider.name == 'custom'
    assert seen == {'service': 'floware', 'default': DEFAULT}


def test_entry_point_must_return_a_provider(monkeypatch):
    class EntryPoint:
        name = 'broken'

        def load(self):
            return lambda **kwargs: object()

    monkeypatch.setattr(
        'authz_module.loader.entry_points', lambda group: [EntryPoint()]
    )
    with pytest.raises(TypeError):
        load_provider(service='svc', default=DEFAULT, name='broken')


# --- hooks -------------------------------------------------------------------


ALICE = user_principal('alice')
AGENT = ResourceRef('agent', 'helper')


class Restrictive(AllowAll):
    async def filter_capabilities(self, principal, agent, capabilities):
        return [c for c in capabilities if c.kind != 'datasource']

    async def authorize_call(self, principal, agent, capability, ctx):
        allowed = capability.attributes.get('datasource_id') != 'secret'
        return Decision(allowed, None if allowed else 'not that one')

    async def before_query(self, principal, query, ctx):
        if query.resource == 'forbidden':
            raise AccessDenied(Decision.deny('no'))
        return DataQuery(
            datasource=query.datasource,
            operation=query.operation,
            resource=query.resource,
            filter="tenant eq 'a'",
        )


@pytest.fixture
def restrictive():
    install(AuthzProvider(StaticAuthenticator(ALICE), Restrictive()))
    yield
    install(None)


async def test_hooks_without_a_provider_change_nothing():
    install(None)
    items = ['a', 'b']
    assert (
        await hooks.filter_capabilities(AGENT, items, lambda i: Capability('tool', i))
        == items
    )
    assert (await hooks.authorize_call(AGENT, Capability('tool', 'a'))).allowed
    query = DataQuery(datasource=ResourceRef('datasource', 'd'), operation='query')
    assert await hooks.before_query(query) is query


async def test_filter_capabilities_keeps_the_callers_items(restrictive):
    items = [('search', 'tool'), ('orders_db', 'datasource')]
    kept = await hooks.filter_capabilities(
        AGENT, items, lambda item: Capability(item[1], item[0]), principal=ALICE
    )
    assert kept == [('search', 'tool')]


async def test_ensure_call_allowed(restrictive):
    await hooks.ensure_call_allowed(
        AGENT, Capability('datasource', 'q'), principal=ALICE
    )
    with pytest.raises(AccessDenied):
        await hooks.ensure_call_allowed(
            AGENT,
            Capability('datasource', 'q', {'datasource_id': 'secret'}),
            principal=ALICE,
        )


async def test_before_query_can_narrow_or_refuse(restrictive):
    query = DataQuery(
        datasource=ResourceRef('datasource', 'd'), operation='query', resource='t'
    )
    assert (await hooks.before_query(query)).filter == "tenant eq 'a'"
    with pytest.raises(AccessDenied):
        await hooks.before_query(
            DataQuery(
                datasource=query.datasource, operation='query', resource='forbidden'
            )
        )
