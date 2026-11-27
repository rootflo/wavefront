"""Authenticate, then authorize against the route's declaration."""

from __future__ import annotations

from typing import Callable, Iterable

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from authz_module.context import RequestContext, reset_current, set_current
from authz_module.dependencies import MISSING_CREDENTIALS, RouteAuthz, decide
from authz_module.principal import ANONYMOUS, Principal
from authz_module.protocols import AuthenticationError
from authz_module.provider import AuthzProvider
from authz_module.routes import declarations, match_route, path_params

ErrorRenderer = Callable[[int, str], Response]


def default_error_renderer(status_code: int, message: str) -> Response:
    return JSONResponse(status_code=status_code, content={'detail': message})


class AuthzMiddleware(BaseHTTPMiddleware):
    """Run every HTTP request through the provider.

    1. Find the route the request will hit and what it declares.
    2. Public routes (``public_route``, or an action whose legacy rule is
       PUBLIC) are served as anonymous with no authentication at all.
    3. Otherwise the authenticator must produce a principal.
    4. Each declared action is authorized against that principal.

    A request that matches no route, or a route that declares nothing, still
    needs an authenticated caller: unknown paths do not become public. A
    service that has never authenticated such requests can pass
    ``authenticate_undeclared=False`` to let them through to the router's
    404/405.

    ``public_paths`` covers framework routes that cannot carry a declaration
    (``/docs``, ``/openapi.json``).
    """

    def __init__(
        self,
        app,
        *,
        provider: AuthzProvider | Callable[[], AuthzProvider],
        render_error: ErrorRenderer = default_error_renderer,
        public_paths: Iterable[str] = (),
        missing_credentials_message: str = MISSING_CREDENTIALS,
        authenticate_undeclared: bool = True,
    ):
        super().__init__(app)
        self._provider = provider
        self.render_error = render_error
        self.public_paths = frozenset(public_paths)
        self.missing_credentials_message = missing_credentials_message
        self.authenticate_undeclared = authenticate_undeclared

    @property
    def provider(self) -> AuthzProvider:
        if not isinstance(self._provider, AuthzProvider):
            self._provider = self._provider()
        return self._provider

    def route_declarations(self, request: Request) -> tuple[RouteAuthz, ...]:
        router = getattr(request.scope.get('app'), 'router', None)
        if router is None:
            return ()
        route, full = match_route(router.routes, request.scope)
        if route is None:
            return ()
        found = declarations(route)
        if full:
            # The router fills path_params only after this middleware has run;
            # resource resolvers need them now. The router overwrites them with
            # the same values later.
            request.scope['path_params'] = path_params(route, request.scope)
            return found
        # Right path, wrong method: the router answers 405. A public path stays
        # public for every method, as the old path-based public lists were.
        if found and all(d.skips_authentication for d in found):
            return (RouteAuthz(public=True),)
        return ()

    async def authenticate(self, request: Request) -> Principal | Response:
        try:
            principal = await self.provider.authenticator.authenticate(request)
        except AuthenticationError as exc:
            return self.render_error(exc.status_code, exc.message)
        if principal is None:
            return self.render_error(
                status.HTTP_401_UNAUTHORIZED, self.missing_credentials_message
            )
        return principal

    async def dispatch(self, request: Request, call_next):
        if request.method == 'OPTIONS':
            return await call_next(request)

        provider = self.provider
        request.state.authz_provider = provider
        found = self.route_declarations(request)

        if found:
            public = all(d.skips_authentication for d in found)
        else:
            public = not self.authenticate_undeclared
        public = public or request.url.path in self.public_paths
        if public:
            principal: Principal = ANONYMOUS
        else:
            result = await self.authenticate(request)
            if isinstance(result, Response):
                return result
            principal = result

        ctx = RequestContext.from_connection(request)
        for declaration in found:
            if declaration.action is None:
                continue
            decision = await decide(
                principal,
                declaration.action.name,
                declaration.resolve_resource(request),
                conn=request,
                ctx=ctx,
            )
            if not decision.allowed:
                if principal.is_anonymous and not decision.status_code:
                    return self.render_error(
                        status.HTTP_401_UNAUTHORIZED, self.missing_credentials_message
                    )
                return self.render_error(
                    decision.status_code or declaration.deny_status,
                    decision.reason or declaration.deny_message or 'Forbidden',
                )

        request.state.principal = principal
        request.state.authz_enforced = True

        tokens = set_current(principal, provider)
        try:
            return await call_next(request)
        finally:
            reset_current(tokens)
