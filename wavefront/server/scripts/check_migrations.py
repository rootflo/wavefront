"""Guard rails for Alembic migrations, run per pull request.

Subcommands, each mapping to one CI step so failures stay legible:

    graph     every tree resolves to exactly one head
    policy    at most one new migration per tree, and no edits to merged ones
    upgrade   `alembic upgrade head` actually applies to an empty database
    drift     models and migrations agree (advisory; see --strict)

``graph`` and ``policy`` need no database. ``upgrade`` and ``drift`` connect
using the standard PG* environment variables and build a scratch database per
tree.

Run the database-free checks locally with::

    python scripts/check_migrations.py graph
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVER_ROOT.parent.parent

# Alembic applies these as data migrations; unset, 17c4ba1a32fe writes NULLs
# into NOT NULL columns and the upgrade dies. Real values come from the
# deployment environment, so any non-empty placeholder works here.
SEED_DEFAULTS = {
    'EMAIL': 'ci@example.com',
    'PASSWORD': 'ci-password',
    'FIRST_NAME': 'CI',
    'LAST_NAME': 'Bot',
}


@dataclass(frozen=True)
class Tree:
    """One Alembic tree: the directory holding its alembic.ini."""

    label: str
    ini_dir: Path
    env_prefix: str
    extensions: tuple[str, ...] = ()

    @property
    def script_location(self) -> Path:
        return self.ini_dir / 'alembic'

    @property
    def versions_prefix(self) -> str:
        """Path of the versions directory relative to the git root."""
        return str((self.script_location / 'versions').relative_to(REPO_ROOT))


TREES = (
    Tree(
        label='db_repo_module',
        ini_dir=SERVER_ROOT / 'modules' / 'db_repo_module' / 'db_repo_module',
        env_prefix='DB',
        # No migration creates this, so a fresh database needs it up front.
        extensions=('vector',),
    ),
    Tree(
        label='floconsole',
        ini_dir=SERVER_ROOT / 'apps' / 'floconsole' / 'floconsole' / 'db',
        env_prefix='CONSOLE_DB',
    ),
)


def _fail(message: str) -> None:
    print(f'FAIL {message}')


def _ok(message: str) -> None:
    print(f'ok   {message}')


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------
def check_graph() -> int:
    """Assert one head per tree.

    On a pull_request event the checkout is the merge commit, so this measures
    the state of the target branch *after* merging. A migration whose
    down_revision no longer points at the target's head, and a target branch
    that gained a migration this branch never saw, both surface here as a
    second head.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    failed = 0
    for tree in TREES:
        config = Config()
        config.set_main_option('script_location', str(tree.script_location))
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()

        if len(heads) == 1:
            _ok(f'{tree.label}: single head {heads[0]}')
            continue

        failed = 1
        _fail(f'{tree.label}: expected 1 head, found {len(heads)}: {", ".join(heads)}')
        for head in heads:
            revision = script.get_revision(head)
            print(f'       {head}  {Path(revision.path).name}')
        print(
            '       Rebase onto the target branch and set down_revision on your\n'
            '       migration to the head it brought in.'
        )
    return failed


# --------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------
def check_policy() -> int:
    """Read `status<TAB>path` lines on stdin, as produced by the GitHub API."""
    entries = []
    for line in sys.stdin:
        line = line.rstrip('\n')
        if not line:
            continue
        status, _, path = line.partition('\t')
        entries.append((status, path))

    if not entries:
        print('no changed files on stdin; nothing to check')
        return 0

    failed = 0
    for tree in TREES:
        prefix = tree.versions_prefix
        touched = [(s, p) for s, p in entries if p.startswith(f'{prefix}/')]
        added = [p for s, p in touched if s == 'added']
        edited = [(s, p) for s, p in touched if s != 'added']

        if len(added) > 1:
            failed = 1
            _fail(f'{tree.label}: {len(added)} new migrations in one PR, expected 1')
            for path in added:
                print(f'       {Path(path).name}')
            print('       Split them across separate pull requests.')
        else:
            _ok(f'{tree.label}: {len(added)} new migration(s)')

        if edited:
            failed = 1
            _fail(f'{tree.label}: migrations already on the target branch were changed')
            for status, path in edited:
                print(f'       {status:9} {Path(path).name}')
            print(
                '       Editing a merged migration desyncs environments that already\n'
                '       ran it. Write a new migration instead.'
            )
    return failed


# --------------------------------------------------------------------------
# database-backed checks
# --------------------------------------------------------------------------
def _scratch_database(tree: Tree) -> dict[str, str]:
    """Create an empty database for this tree and return env pointing at it."""
    import sqlalchemy as sa

    host = os.environ.get('PGHOST', 'localhost')
    port = os.environ.get('PGPORT', '5432')
    user = os.environ.get('PGUSER', 'postgres')
    password = os.environ.get('PGPASSWORD', 'postgres')
    name = f'migcheck_{tree.label}'

    base = sa.engine.URL.create(
        'postgresql+psycopg',
        username=user,
        password=password,
        host=host,
        port=int(port),
        database='postgres',
    )

    admin = sa.create_engine(base, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS {name}')
        conn.exec_driver_sql(f'CREATE DATABASE {name}')
    admin.dispose()

    if tree.extensions:
        scratch = sa.create_engine(
            base.set(database=name), isolation_level='AUTOCOMMIT'
        )
        with scratch.connect() as conn:
            for extension in tree.extensions:
                conn.exec_driver_sql(f'CREATE EXTENSION IF NOT EXISTS {extension}')
        scratch.dispose()

    env = {**os.environ, **{k: os.environ.get(k, v) for k, v in SEED_DEFAULTS.items()}}
    # knowledge_base_embeddings declares Vector outside tests and Text under
    # APP_ENV=test. Leaving it set would compare a Text model against a VECTOR
    # column and report drift that does not exist in any real environment.
    env.pop('APP_ENV', None)
    env.update(
        {
            f'{tree.env_prefix}_USERNAME': user,
            f'{tree.env_prefix}_PASSWORD': password,
            f'{tree.env_prefix}_HOST': host,
            f'{tree.env_prefix}_PORT': port,
            f'{tree.env_prefix}_NAME': name,
        }
    )
    return env


def _alembic(tree: Tree, env: dict[str, str], *args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', *args],
        cwd=tree.ini_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def check_upgrade() -> int:
    failed = 0
    for tree in TREES:
        env = _scratch_database(tree)
        code, output = _alembic(tree, env, 'upgrade', 'head')
        if code == 0:
            _ok(f'{tree.label}: upgrade head applies to an empty database')
        else:
            failed = 1
            _fail(f'{tree.label}: upgrade head failed')
            print('\n'.join(f'       {line}' for line in output.splitlines()[-30:]))
    return failed


def _summarise_operations(output: str) -> collections.Counter:
    """Tally the operation kinds alembic reports, which it emits as one long line.

    Anchored to the add_/remove_/modify_ prefixes every autogenerate operation
    uses, so column and index names quoted inside the same line are not counted.
    """
    return collections.Counter(re.findall(r"\('((?:add|remove|modify)_\w+)',", output))


def check_drift(strict: bool) -> int:
    """Compare models against the schema the migrations build.

    There are 59 known discrepancies predating this check (56 in db_repo_module,
    3 in floconsole), so it reports without failing unless --strict is passed.
    Flip CI to --strict once that backlog is cleared.
    """
    drifted = 0
    for tree in TREES:
        env = _scratch_database(tree)
        code, output = _alembic(tree, env, 'upgrade', 'head')
        if code != 0:
            drifted = 1
            _fail(f'{tree.label}: cannot check drift, upgrade head failed')
            continue

        code, output = _alembic(tree, env, 'check')
        if code == 0:
            _ok(f'{tree.label}: models match migrations')
        else:
            drifted = 1
            kinds = _summarise_operations(output)
            total = sum(kinds.values())
            _fail(f'{tree.label}: {total} differences between models and migrations')
            for kind, count in kinds.most_common():
                print(f'       {kind:<20} {count}')
            relative = tree.ini_dir.relative_to(SERVER_ROOT)
            print(f'       Reproduce with: cd {relative} && alembic check')

    if drifted and not strict:
        print(
            '\nAdvisory only: this step does not fail the build. Pass --strict once\n'
            'the existing drift is resolved to make it blocking.'
        )
        return 0
    return drifted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=('graph', 'policy', 'upgrade', 'drift'))
    parser.add_argument(
        '--strict',
        action='store_true',
        help='make the drift check fail the build',
    )
    args = parser.parse_args()

    if args.check == 'graph':
        return check_graph()
    if args.check == 'policy':
        return check_policy()
    if args.check == 'upgrade':
        return check_upgrade()
    return check_drift(strict=args.strict)


if __name__ == '__main__':
    sys.exit(main())
