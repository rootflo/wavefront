"""Run and inspect app migrations.

    python -m floware.app_migrations status
    python -m floware.app_migrations upgrade --dry-run
    python -m floware.app_migrations upgrade [--only REV]
    python -m floware.app_migrations downgrade REV [--dry-run]
    python -m floware.app_migrations stamp REV
    python -m floware.app_migrations new "short description"

`upgrade` takes a database lock, brings the schema to the Alembic head, then
runs every due migration in chain order. With --dry-run it changes nothing:
not the schema, not the data, not the ledger.

`downgrade` reverts one migration under the same lock and records it as
`reverted`, which makes it pending again. The schema is left as it is.

In the floware image: `docker run <image> app-migrate <command> ...`.
Settings come from floware's .env when it exists (it wins over exported
variables; --env-file picks another), otherwise from the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from floware.app_migrations.context import (
    DEFAULT_ENV_FILE,
    AppMigrationContext,
    build_container,
    load_env_file,
)
from floware.app_migrations.ledger import AppMigrationLedger
from floware.app_migrations.registry import (
    MAX_DESCRIPTION_LENGTH,
    VERSIONS_DIR,
    AppMigrationScript,
    chain_head,
    load_migrations,
)
from floware.app_migrations.runner import (
    MigrationState,
    advisory_lock,
    migration_states,
    run_downgrade,
    run_pending,
    schema_heads,
)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='python -m floware.app_migrations',
        description='Run and inspect one-time app migrations.',
    )
    parser.add_argument(
        '--env-file',
        default=str(DEFAULT_ENV_FILE),
        help="env file to load (default: floware's .env); it wins over exported variables",
    )
    commands = parser.add_subparsers(dest='command', required=True)

    commands.add_parser('status', help='show every migration and its state here')

    upgrade = commands.add_parser('upgrade', help='run every due migration')
    upgrade.add_argument(
        '--dry-run',
        action='store_true',
        help='report what would change; write nothing',
    )
    upgrade.add_argument('--only', metavar='REV', help='run just this revision')

    downgrade = commands.add_parser('downgrade', help='revert one applied migration')
    downgrade.add_argument('revision')
    downgrade.add_argument(
        '--dry-run',
        action='store_true',
        help='report what would change; write nothing',
    )

    stamp = commands.add_parser(
        'stamp', help='record a revision applied without running it'
    )
    stamp.add_argument('revision')

    new = commands.add_parser('new', help='create a migration file at the head')
    new.add_argument('description')

    return parser.parse_args(argv)


def _print_states(states: List[MigrationState]) -> None:
    if not states:
        print('No app migrations defined')
        return
    print(f'{"REVISION":<14}{"STATE":<26}{"BLOCKING":<10}DESCRIPTION')
    for state in states:
        shown = state.state
        if state.waiting_on:
            shown = f'waiting on {", ".join(state.waiting_on)}'
        if state.reverted:
            shown = f'{shown} (reverted)'
        blocking = 'yes' if state.script.blocking else 'no'
        print(
            f'{state.script.revision:<14}{shown:<26}{blocking:<10}'
            f'{state.script.description}'
        )
        if state.error:
            print(f'{"":<14}last error: {state.error.strip().splitlines()[-1]}')


async def _status(ctx: AppMigrationContext, scripts: List[AppMigrationScript]) -> int:
    ledger = AppMigrationLedger(ctx.db_client)
    if not await ledger.table_exists():
        print('The app_migrations table does not exist yet (schema behind head)')
    entries = await ledger.entries()
    _print_states(migration_states(scripts, entries, ctx.feature_flags))
    return 0


async def _upgrade(
    ctx: AppMigrationContext, scripts: List[AppMigrationScript], only: str | None
) -> int:
    db_client = ctx.db_client
    async with advisory_lock(db_client):
        current, heads = await schema_heads(db_client)
        if current != heads:
            if ctx.dry_run:
                print(
                    f'[dry-run] schema is at {sorted(current) or "nothing"}, '
                    f'head is {sorted(heads)}; a real run upgrades it first'
                )
            else:
                print(f'Upgrading schema to {", ".join(sorted(heads))}')
                db_client.run_migration()

        ledger = AppMigrationLedger(db_client, app_version=ctx.app_version)
        result = await run_pending(scripts, ledger, ctx, only=only)

    prefix = '[dry-run] ' if ctx.dry_run else ''
    verb = 'would apply' if ctx.dry_run else 'applied'
    print(f'{prefix}{len(result.applied)} app migration(s) {verb}')
    return 0 if result.ok else 1


async def _downgrade(
    ctx: AppMigrationContext, scripts: List[AppMigrationScript], revision: str
) -> int:
    async with advisory_lock(ctx.db_client):
        ledger = AppMigrationLedger(ctx.db_client, app_version=ctx.app_version)
        result = await run_downgrade(scripts, ledger, ctx, revision)
    return 0 if result.ok else 1


async def _stamp(
    ctx: AppMigrationContext, scripts: List[AppMigrationScript], revision: str
) -> int:
    script = next((s for s in scripts if s.revision == revision), None)
    if script is None:
        print(f'Unknown app migration revision {revision}')
        return 1
    async with advisory_lock(ctx.db_client):
        ledger = AppMigrationLedger(ctx.db_client, app_version=ctx.app_version)
        await ledger.stamp(script.revision, script.description, applied_by='stamp')
    print(f'{script.revision} ({script.description}) recorded as applied')
    return 0


_TEMPLATE = '''"""{description}

<What this changes on every deployment, and why Alembic cannot do it.>
"""

from common_module.feature.feature_flag import FeatureFlags
from floware.app_migrations.context import AppMigrationContext

revision = '{revision}'
down_revision = {down_revision}
description = '{description}'
# True: floware refuses to start while this applies and is not applied.
blocking = False
# Revisions that must be applied first; this one waits for them otherwise.
depends_on = ()


def applies(flags: FeatureFlags) -> bool:
    """False leaves the migration pending until it does apply."""
    return True


async def upgrade(ctx: AppMigrationContext) -> dict:
    """Must be idempotent, and change nothing when ctx.dry_run is set.

    The returned dict is stored as the ledger row's summary.
    """
    return {{}}


async def verify(ctx: AppMigrationContext) -> list[str]:
    """Problems left after upgrade; any of them marks the run failed."""
    return []


async def downgrade(ctx: AppMigrationContext) -> dict:
    """Revert upgrade; delete it if the change cannot be reverted.

    Must be idempotent, change nothing when ctx.dry_run is set, and raise if
    the revert is incomplete. The returned dict is stored as the summary.
    """
    return {{}}
'''


def _new(description: str) -> int:
    if len(description) > MAX_DESCRIPTION_LENGTH:
        print(f'Description is longer than {MAX_DESCRIPTION_LENGTH} characters')
        return 1
    revision = uuid.uuid4().hex[:12]
    slug = re.sub(r'[^a-z0-9]+', '_', description.lower()).strip('_')[:40]
    name = f'{datetime.now():%Y_%m_%d_%H%M}-{revision}_{slug}.py'
    head = chain_head()
    path: Path = VERSIONS_DIR / name
    path.write_text(
        _TEMPLATE.format(
            description=description.replace("'", "\\'"),
            revision=revision,
            down_revision=repr(head),
        )
    )
    print(f'Created {path}')
    return 0


async def _run(args: argparse.Namespace) -> int:
    if args.command == 'new':
        return _new(args.description)

    # Before the migrations are imported: modules they pull in may read env.
    load_env_file(Path(args.env_file))
    scripts = load_migrations()
    ctx = AppMigrationContext(
        build_container(), dry_run=getattr(args, 'dry_run', False)
    )
    try:
        if args.command == 'status':
            return await _status(ctx, scripts)
        if args.command == 'upgrade':
            return await _upgrade(ctx, scripts, args.only)
        if args.command == 'downgrade':
            return await _downgrade(ctx, scripts, args.revision)
        return await _stamp(ctx, scripts, args.revision)
    finally:
        await ctx.db_client.close()


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_run(args))
