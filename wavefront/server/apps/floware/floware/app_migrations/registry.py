"""Discover the app migrations in versions/ and order them by their chain."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSIONS_DIR = Path(__file__).resolve().parent / 'versions'

# Length of app_migrations.description.
MAX_DESCRIPTION_LENGTH = 255


class AppMigrationGraphError(Exception):
    """The migration files do not form a single valid chain."""


@dataclass(frozen=True)
class AppMigrationScript:
    revision: str
    down_revision: Optional[str]
    description: str
    blocking: bool
    depends_on: Tuple[str, ...]
    path: Path
    module: ModuleType

    def applies(self, flags: Any) -> bool:
        check = getattr(self.module, 'applies', None)
        return True if check is None else bool(check(flags))

    async def upgrade(self, ctx: Any) -> Dict[str, Any]:
        return await self.module.upgrade(ctx) or {}

    async def verify(self, ctx: Any) -> List[str]:
        check = getattr(self.module, 'verify', None)
        return [] if check is None else list(await check(ctx))

    @property
    def reversible(self) -> bool:
        return getattr(self.module, 'downgrade', None) is not None

    async def downgrade(self, ctx: Any) -> Dict[str, Any]:
        return await self.module.downgrade(ctx) or {}


def _version_files(versions_dir: Path) -> List[Path]:
    return sorted(p for p in versions_dir.glob('*.py') if not p.name.startswith('_'))


def load_migrations(versions_dir: Path = VERSIONS_DIR) -> List[AppMigrationScript]:
    """Every migration in ``versions_dir``, in chain order (root first)."""
    return order_chain(_load(path) for path in _version_files(versions_dir))


def chain_head(versions_dir: Path = VERSIONS_DIR) -> Optional[str]:
    """The last revision in the chain, read without importing the files.

    Importing pulls in most of floware, which needs its env loaded first.
    """
    parents: Dict[str, Optional[str]] = {}
    for path in _version_files(versions_dir):
        values = {}
        for node in ast.parse(path.read_text()).body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ('revision', 'down_revision')
            ):
                values[node.targets[0].id] = ast.literal_eval(node.value)
        if 'revision' not in values or 'down_revision' not in values:
            raise AppMigrationGraphError(
                f'{path.name} needs literal `revision` and `down_revision`'
            )
        parents[values['revision']] = values['down_revision']
    if not parents:
        return None
    heads = set(parents) - set(parents.values())
    if len(heads) != 1:
        found = ', '.join(sorted(heads)) or 'none'
        raise AppMigrationGraphError(f'Expected one app migration head, found {found}')
    return heads.pop()


def order_chain(scripts: Iterable[AppMigrationScript]) -> List[AppMigrationScript]:
    scripts = list(scripts)
    if not scripts:
        return []

    by_revision: Dict[str, AppMigrationScript] = {}
    for script in scripts:
        if script.revision in by_revision:
            raise AppMigrationGraphError(
                f'Duplicate app migration revision {script.revision}: '
                f'{by_revision[script.revision].path.name}, {script.path.name}'
            )
        by_revision[script.revision] = script

    children: Dict[Optional[str], List[AppMigrationScript]] = {}
    for script in scripts:
        if script.down_revision is not None and script.down_revision not in by_revision:
            raise AppMigrationGraphError(
                f'App migration {script.revision} revises unknown revision '
                f'{script.down_revision}'
            )
        children.setdefault(script.down_revision, []).append(script)

    for parent, kids in children.items():
        if len(kids) > 1:
            names = ', '.join(kid.revision for kid in kids)
            where = 'root' if parent is None else f'revision {parent}'
            raise AppMigrationGraphError(
                f'App migrations {names} all follow {where}; the chain must be linear'
            )

    ordered: List[AppMigrationScript] = []
    current = children.get(None, [None])[0]
    while current is not None:
        ordered.append(current)
        current = children.get(current.revision, [None])[0]
    if len(ordered) != len(scripts):
        unreachable = sorted(set(by_revision) - {s.revision for s in ordered})
        raise AppMigrationGraphError(
            f'App migrations not reachable from the root: {", ".join(unreachable)}'
        )

    position = {script.revision: index for index, script in enumerate(ordered)}
    for script in ordered:
        for dependency in script.depends_on:
            if position.get(dependency, len(ordered)) >= position[script.revision]:
                raise AppMigrationGraphError(
                    f'App migration {script.revision} depends on {dependency}, '
                    'which is not an earlier revision in the chain'
                )
    return ordered


def _load(path: Path) -> AppMigrationScript:
    # File names start with a date, so they are not importable by name.
    module_name = 'floware_app_migration_' + re.sub(r'\W', '_', path.stem)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ('revision', 'down_revision', 'description', 'upgrade'):
        if not hasattr(module, attr):
            raise AppMigrationGraphError(f'{path.name} does not define `{attr}`')
    if not inspect.iscoroutinefunction(module.upgrade):
        raise AppMigrationGraphError(f'{path.name}: `upgrade` must be async')
    if len(module.description) > MAX_DESCRIPTION_LENGTH:
        raise AppMigrationGraphError(
            f'{path.name}: `description` is longer than '
            f'{MAX_DESCRIPTION_LENGTH} characters'
        )
    for optional in ('verify', 'downgrade'):
        function = getattr(module, optional, None)
        if function is not None and not inspect.iscoroutinefunction(function):
            raise AppMigrationGraphError(f'{path.name}: `{optional}` must be async')

    return AppMigrationScript(
        revision=module.revision,
        down_revision=module.down_revision,
        description=module.description,
        blocking=bool(getattr(module, 'blocking', False)),
        depends_on=tuple(getattr(module, 'depends_on', ()) or ()),
        path=path,
        module=module,
    )
