"""``authz export-catalog`` and ``authz lint-routes``.

A target is ``module:attribute`` naming a FastAPI app, an APIRouter, a list of
either, or a zero-argument callable returning one of those.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import FastAPI
from fastapi.routing import APIRouter
from starlette.routing import BaseRoute

from authz_module.actions import ActionSpec
from authz_module.routes import (
    declarations,
    is_endpoint,
    iter_routes,
    original_route,
    route_methods,
)


@dataclass(frozen=True)
class RouteEntry:
    path: str
    methods: tuple[str, ...]
    endpoint: str
    public: bool
    actions: tuple[ActionSpec, ...]

    @property
    def annotated(self) -> bool:
        return self.public or bool(self.actions)

    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'methods': list(self.methods),
            'endpoint': self.endpoint,
            'public': self.public,
            'actions': [spec.name for spec in self.actions],
            'legacy': [str(spec.legacy) for spec in self.actions],
        }


def load_target(target: str) -> Any:
    module_name, _, attr = target.partition(':')
    if not attr:
        raise SystemExit(f'Target {target!r} must be module:attribute')
    obj: Any = importlib.import_module(module_name)
    for part in attr.split('.'):
        obj = getattr(obj, part)
    if callable(obj) and not isinstance(obj, (FastAPI, APIRouter)):
        obj = obj()
    return obj


def _routes_of(obj: Any) -> list[BaseRoute]:
    if isinstance(obj, (FastAPI, APIRouter)):
        return list(obj.routes)
    if isinstance(obj, (list, tuple)):
        routes: list[BaseRoute] = []
        for item in obj:
            routes.extend(_routes_of(item))
        return routes
    raise SystemExit(f'Cannot read routes from {type(obj).__name__}')


def collect(obj: Any) -> list[RouteEntry]:
    """Every endpoint route in ``obj`` and what it declares."""
    entries = []
    for route in iter_routes(_routes_of(obj)):
        if not is_endpoint(route):
            continue
        found = declarations(route)
        endpoint = getattr(original_route(route), 'endpoint', None)
        entries.append(
            RouteEntry(
                path=getattr(route, 'path', None)
                or getattr(original_route(route), 'path', '?'),
                methods=tuple(route_methods(route)),
                endpoint=(
                    f'{endpoint.__module__}.{endpoint.__qualname__}'
                    if endpoint is not None
                    else '?'
                ),
                public=any(d.public for d in found),
                actions=tuple(d.action for d in found if d.action is not None),
            )
        )
    return sorted(entries, key=lambda e: (e.path, e.methods))


def catalog(entries: Iterable[RouteEntry]) -> dict:
    entries = list(entries)
    actions: dict[str, ActionSpec] = {}
    for entry in entries:
        for spec in entry.actions:
            actions[spec.name] = spec
    # Actions checked inside handlers (define_action) are registered on import.
    from authz_module.actions import all_actions

    for spec in all_actions():
        actions.setdefault(spec.name, spec)
    return {
        'actions': [actions[name].to_dict() for name in sorted(actions)],
        'routes': [entry.to_dict() for entry in entries],
    }


def lint(entries: Iterable[RouteEntry]) -> list[str]:
    problems = []
    for entry in entries:
        if not entry.annotated:
            problems.append(
                f'{",".join(entry.methods)} {entry.path} ({entry.endpoint}) '
                'declares neither requires(...) nor public_route'
            )
        elif entry.public and entry.actions:
            problems.append(
                f'{",".join(entry.methods)} {entry.path} ({entry.endpoint}) '
                'is both public_route and requires(...)'
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='authz')
    sub = parser.add_subparsers(dest='command', required=True)

    export = sub.add_parser('export-catalog', help='Print every action as JSON')
    export.add_argument('targets', nargs='+')
    export.add_argument('--out', help='Write to this file instead of stdout')

    lint_cmd = sub.add_parser(
        'lint-routes', help='Fail if any route lacks requires() or public_route'
    )
    lint_cmd.add_argument('targets', nargs='+')

    snap = sub.add_parser(
        'snapshot',
        help='Catalog plus the access matrix (route x principal -> status), as JSON',
    )
    snap.add_argument('target')
    snap.add_argument('--out', help='Write to this file instead of stdout')
    snap.add_argument(
        '--allow-undeclared',
        action='store_true',
        help='The service lets requests to unknown paths through unauthenticated',
    )
    snap.add_argument('--public-path', action='append', default=[])

    args = parser.parse_args(argv)
    if args.command == 'snapshot':
        return _snapshot(args)
    entries: list[RouteEntry] = []
    for target in args.targets:
        entries.extend(collect(load_target(target)))

    if args.command == 'export-catalog':
        text = json.dumps(catalog(entries), indent=2) + '\n'
        if args.out:
            with open(args.out, 'w') as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
        return 0

    problems = lint(entries)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f'{len(problems)} route(s) not annotated', file=sys.stderr)
        return 1
    print(f'{len(entries)} routes annotated')
    return 0


def snapshot(target: str, *, allow_undeclared: bool = False, public_paths=()) -> dict:
    from authz_module.matrix import access_matrix

    obj = load_target(target)
    data = catalog(collect(obj))
    problems = lint(collect(obj))
    # The matrix replaces handlers, so it gets an app of its own.
    data['access'] = access_matrix(
        load_target(target),
        authenticate_undeclared=not allow_undeclared,
        public_paths=public_paths,
    )
    data['unannotated'] = problems
    return data


def _snapshot(args) -> int:
    text = (
        json.dumps(
            snapshot(
                args.target,
                allow_undeclared=args.allow_undeclared,
                public_paths=args.public_path,
            ),
            indent=2,
            sort_keys=True,
        )
        + '\n'
    )
    if args.out:
        with open(args.out, 'w') as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
