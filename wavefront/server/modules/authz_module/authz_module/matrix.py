"""The access matrix: what status every route gives every kind of caller.

Each route is called once per method for a fixed set of principals, through
``AuthzMiddleware`` and the default authorizer, with the handler replaced by a
stub that answers 200. The result records, per route, the action the request
resolved to and the status class each principal got -- the behaviour the
authorization layer is responsible for, with nothing else in the way.

Role questions are answered from the principal itself (``StubResolver``), so the
matrix checks which rule each route carries and how it is enforced, not any one
service's role tables. Committed per service, it is the snapshot a change to
access has to show up in.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.routing import request_response
from starlette.testclient import TestClient

from authz_module.default import DefaultAuthorizer
from authz_module.middleware import AuthzMiddleware
from authz_module.principal import Principal, user_principal
from authz_module.provider import AuthzProvider
from authz_module.routes import (
    declarations,
    is_endpoint,
    iter_routes,
    match_route,
    original_route,
)

PRINCIPAL_HEADER = 'X-Authz-Matrix-Principal'
ROLES_ATTRIBUTE = 'matrix_roles'


def _principal(name: str, *roles: str) -> Principal:
    return user_principal(
        f'matrix-{name}', role_id=name, attributes={ROLES_ATTRIBUTE: ','.join(roles)}
    )


#: Name -> principal (None: presents no credentials).
PRINCIPALS: dict[str, Principal | None] = {
    'anonymous': None,
    'user': _principal('user'),
    'manager': _principal('manager', 'manager'),
    'admin': _principal('admin', 'admin'),
    'console_user': _principal('console_user', 'console'),
    'user_with_flags': _principal('user_with_flags', 'flags'),
}


class StubResolver:
    """Answers legacy rules from the principal's ``matrix_roles`` attribute."""

    @staticmethod
    def _roles(principal: Principal) -> set[str]:
        return set(
            filter(None, principal.attributes.get(ROLES_ATTRIBUTE, '').split(','))
        )

    async def is_admin(self, principal):
        return 'admin' in self._roles(principal)

    async def is_manager(self, principal):
        return 'manager' in self._roles(principal)

    async def is_console_user(self, principal):
        return 'console' in self._roles(principal)

    async def has_resource_scope(self, principal, scope):
        return f'scope:{scope}' in self._roles(principal)

    def flag_enabled(self, flag):
        # Flags are per deployment, not per caller: on only for the principal
        # that carries them, so one matrix shows both settings.
        from authz_module.context import current_principal

        principal = current_principal()
        return principal is not None and 'flags' in self._roles(principal)


class _HeaderAuthenticator:
    def __init__(self, principals: Mapping[str, Principal | None]):
        self.principals = principals

    async def authenticate(self, conn: HTTPConnection) -> Principal | None:
        return self.principals.get(conn.headers.get(PRINCIPAL_HEADER, ''))


class _FlagAwareAuthorizer(DefaultAuthorizer):
    async def authorize(self, principal, action, resource, ctx):
        from authz_module.context import _current_principal

        token = _current_principal.set(principal)
        try:
            return await super().authorize(principal, action, resource, ctx)
        finally:
            _current_principal.reset(token)


async def _ok(request):
    return PlainTextResponse('ok')


def _stub(route: APIRoute) -> None:
    # Included routes build their handler per request; direct ones keep `app`.
    route.get_route_handler = lambda: _ok  # type: ignore[method-assign]
    route.app = request_response(_ok)


def _sample_path(path: str) -> str:
    return re.sub(r'\{[^}:]+(:[^}]+)?\}', 'p1', path)


def access_matrix(
    app: FastAPI,
    *,
    principals: Mapping[str, Principal | None] = PRINCIPALS,
    authenticate_undeclared: bool = True,
    public_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """``{"METHOD /path": {"action": ..., "status": {principal: code}}}``.

    Replaces every handler of ``app`` with a stub: build ``app`` for this only.
    """
    endpoints = []
    for route in iter_routes(app.router.routes):
        if not is_endpoint(route):
            continue
        original = original_route(route)
        if not isinstance(original, APIRoute):
            continue  # websockets are not served through the middleware
        _stub(original)
        endpoints.append(route)

    app.add_middleware(
        AuthzMiddleware,
        provider=AuthzProvider(
            authenticator=_HeaderAuthenticator(principals),
            authorizer=_FlagAwareAuthorizer(StubResolver()),
            name='matrix',
        ),
        authenticate_undeclared=authenticate_undeclared,
        public_paths=public_paths,
    )
    client = TestClient(app, raise_server_exceptions=True)

    matrix: dict[str, Any] = {}
    for route in endpoints:
        path = getattr(route, 'path', None) or original_route(route).path
        for method in sorted(route.methods or []):
            sample = _sample_path(path)
            resolved, _ = match_route(
                app.router.routes, {'type': 'http', 'path': sample, 'method': method}
            )
            found = declarations(resolved) if resolved is not None else ()
            statuses = {}
            for name in principals:
                response = client.request(
                    method, sample, headers={PRINCIPAL_HEADER: name}
                )
                statuses[name] = response.status_code
            matrix[f'{method} {path}'] = {
                'resolves_to': sorted(
                    'public' if d.public else d.action.name
                    for d in found
                    if d.public or d.action is not None
                ),
                'status': statuses,
            }
    return dict(sorted(matrix.items()))
