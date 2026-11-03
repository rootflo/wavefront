"""Finding the route a request will hit, and what it declares.

FastAPI (0.13x+) no longer copies an included router's routes into the app: it
keeps the router and resolves its routes lazily, combining router-level
dependencies and prefixes on the way. ``fastapi.routing.iter_route_contexts``
is the supported view of the result -- one context per effective route, in
routing order, carrying the combined ``dependant`` and ``path_regex``. Older
FastAPI copies routes, so plain iteration gives the same thing.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import BaseRoute
from starlette.types import Scope

from authz_module.dependencies import RouteAuthz

try:  # FastAPI >= 0.13x
    from fastapi.routing import iter_route_contexts as _iter_route_contexts
except ImportError:  # pragma: no cover - older FastAPI copies included routes
    _iter_route_contexts = None


def iter_routes(routes: Iterable[BaseRoute]) -> Iterator[Any]:
    """Every effective route, flattened, in the order the router tries them."""
    if _iter_route_contexts is not None:
        yield from _iter_route_contexts(list(routes))
        return
    for route in routes:  # pragma: no cover
        nested = getattr(route, 'routes', None)
        if nested is not None and not isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield from iter_routes(nested)
        else:
            yield route


def original_route(route: Any) -> BaseRoute:
    return getattr(route, 'original_route', route)


def is_endpoint(route: Any) -> bool:
    return isinstance(original_route(route), (APIRoute, APIWebSocketRoute))


def _walk(dependant: Dependant, seen: set[int]) -> Iterator[RouteAuthz]:
    for sub in dependant.dependencies:
        call = sub.call
        declaration = getattr(call, '__authz__', None)
        if isinstance(declaration, RouteAuthz) and id(call) not in seen:
            seen.add(id(call))
            yield declaration
        yield from _walk(sub, seen)


def declarations(route: Any) -> tuple[RouteAuthz, ...]:
    """Every ``requires``/``public_route`` on a route, router-level ones included."""
    dependant = getattr(route, 'dependant', None)
    if not isinstance(dependant, Dependant):
        # Websocket routes inside an included router expose no combined
        # dependant; their own carries the route-level declarations.
        dependant = getattr(original_route(route), 'dependant', None)
    if not isinstance(dependant, Dependant):
        return ()
    cached = getattr(dependant, '_authz_declarations', None)
    if cached is not None:
        return cached
    found = tuple(_walk(dependant, set()))
    try:
        dependant._authz_declarations = found  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        pass
    return found


def route_path(scope: Scope) -> str:
    """The path the router matches against (``root_path`` removed)."""
    path = scope['path']
    root_path = scope.get('root_path', '')
    if not root_path or not path.startswith(root_path) or path == root_path:
        return path
    if path[len(root_path)] == '/':
        return path[len(root_path) :]
    return path


def _method_allowed(route: Any, method: str | None) -> bool:
    methods = getattr(route, 'methods', None)
    if not methods or method is None:
        return True
    return method in methods or (method == 'HEAD' and 'GET' in methods)


def match_route(routes: Iterable[BaseRoute], scope: Scope) -> tuple[Any, bool]:
    """The route that will serve ``scope`` and whether it matched fully.

    A full match is path and method. When no route matches fully, the first
    route whose path matches is returned with False: the router will answer
    405, and the caller decides how to treat that. ``(None, False)`` means no
    route has the path.
    """
    path = route_path(scope)
    method = scope.get('method')
    partial = None
    for route in iter_routes(routes):
        regex = getattr(route, 'path_regex', None)
        if regex is None or not regex.match(path):
            continue
        if isinstance(original_route(route), APIWebSocketRoute):
            continue
        if _method_allowed(route, method):
            return route, True
        if partial is None:
            partial = route
    return partial, False


def path_params(route: Any, scope: Scope) -> dict[str, Any]:
    """The path parameters ``route`` extracts from ``scope``, converted."""
    match = route.path_regex.match(route_path(scope))
    if match is None:
        return {}
    convertors = getattr(route, 'param_convertors', None) or {}
    params = dict(scope.get('path_params') or {})
    for key, value in match.groupdict().items():
        convertor = convertors.get(key)
        params[key] = convertor.convert(value) if convertor else value
    return params


def route_methods(route: Any) -> list[str]:
    if isinstance(original_route(route), APIWebSocketRoute):
        return ['WEBSOCKET']
    return sorted(getattr(route, 'methods', None) or [])
