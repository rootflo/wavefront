"""Decide which app migrations are due and run them, recording each in the ledger."""

from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text

from db_repo_module.database.connection import DatabaseClient
from floware.app_migrations.ledger import (
    APPLIED,
    FAILED,
    REVERTED,
    RUNNING,
    LedgerEntry,
)
from floware.app_migrations.registry import AppMigrationScript

# Arbitrary, fixed key for pg_advisory_lock; one app-migration run at a time
# per database.
ADVISORY_LOCK_KEY = 0x666C_6F77_6D69_6772

PENDING, NOT_APPLICABLE, WAITING = 'pending', 'not applicable', 'waiting'

# Verify problems kept in the ledger's error column; the CLI prints them all.
_MAX_RECORDED_PROBLEMS = 20


@dataclass(frozen=True)
class MigrationState:
    script: AppMigrationScript
    # applied | running | failed | pending | not applicable | waiting
    state: str
    waiting_on: Tuple[str, ...] = ()
    error: Optional[str] = None
    # Downgraded earlier; the state is worked out as if it never ran.
    reverted: bool = False


def _applicable(
    scripts: Sequence[AppMigrationScript], applied: set, flags: Any
) -> Dict[str, bool]:
    """Whether each migration applies here.

    One that depends on an unapplied migration that does not apply here does
    not apply either: otherwise it would wait forever, and if blocking, keep
    floware from starting.
    """
    result: Dict[str, bool] = {}
    for script in scripts:
        result[script.revision] = script.applies(flags) and all(
            dependency in applied or result.get(dependency, False)
            for dependency in script.depends_on
        )
    return result


def migration_states(
    scripts: Sequence[AppMigrationScript],
    entries: Dict[str, LedgerEntry],
    flags: Any,
) -> List[MigrationState]:
    """Where each migration stands on this deployment, in chain order."""
    applied = {rev for rev, entry in entries.items() if entry.status == APPLIED}
    applicable = _applicable(scripts, applied, flags)
    states = []
    for script in scripts:
        entry = entries.get(script.revision)
        reverted = entry is not None and entry.status == REVERTED
        if entry is not None and entry.status == APPLIED:
            states.append(MigrationState(script, APPLIED))
        # Before applicability: a run that stopped part way may have left data
        # half converted, whatever the flags say now.
        elif entry is not None and entry.status in (RUNNING, FAILED):
            states.append(MigrationState(script, entry.status, error=entry.error))
        elif not applicable[script.revision]:
            states.append(MigrationState(script, NOT_APPLICABLE, reverted=reverted))
        elif missing := tuple(d for d in script.depends_on if d not in applied):
            states.append(
                MigrationState(script, WAITING, waiting_on=missing, reverted=reverted)
            )
        else:
            states.append(MigrationState(script, PENDING, reverted=reverted))
    return states


def pending_blocking(
    scripts: Sequence[AppMigrationScript],
    entries: Dict[str, LedgerEntry],
    flags: Any,
) -> List[AppMigrationScript]:
    """Blocking migrations that apply here and are not applied, or whose last run stopped part way."""
    return [
        state.script
        for state in migration_states(scripts, entries, flags)
        if state.script.blocking and state.state not in (APPLIED, NOT_APPLICABLE)
    ]


@dataclass
class RunResult:
    applied: List[str] = field(default_factory=list)
    reverted: List[str] = field(default_factory=list)
    failed: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.failed is None


async def run_pending(
    scripts: Sequence[AppMigrationScript],
    ledger: Any,
    ctx: Any,
    *,
    only: Optional[str] = None,
    applied_by: str = 'cli',
) -> RunResult:
    """Run every due migration in chain order; stop at the first failure.

    A migration that does not apply, or waits on one that is not applied, is
    left pending and the run moves on. With ``ctx.dry_run`` each due migration
    reports what it would change and nothing is written to the ledger.
    """
    flags = ctx.feature_flags
    entries = await ledger.entries()
    applied = {rev for rev, entry in entries.items() if entry.status == APPLIED}
    applicable = _applicable(scripts, applied, flags)
    prefix = '[dry-run] ' if ctx.dry_run else ''
    result = RunResult()

    if only is not None and only not in {script.revision for script in scripts}:
        print(f'Unknown app migration revision {only}')
        result.failed = only
        return result

    for script in scripts:
        if only is not None and script.revision != only:
            continue
        label = f'{script.revision} ({script.description})'

        if script.revision in applied:
            if only is not None:
                print(f'{label}: already applied')
            continue
        if not applicable[script.revision]:
            print(f'{label}: not applicable here, left pending')
            if only is not None:
                result.failed = script.revision
            continue
        missing = [d for d in script.depends_on if d not in applied]
        if missing:
            print(f'{label}: waiting on {", ".join(missing)}, left pending')
            if only is not None:
                result.failed = script.revision
            continue

        print(f'{prefix}{label}: running')
        if ctx.dry_run:
            try:
                await script.upgrade(ctx)
            except Exception:
                print(traceback.format_exc())
                print(f'{prefix}{label}: failed')
                result.failed = script.revision
                return result
            # Dependents are planned as if this one applied, so the dry run
            # shows the whole sequence a real run would take.
            applied.add(script.revision)
            result.applied.append(script.revision)
            continue

        await ledger.mark_running(script.revision, script.description, applied_by)
        try:
            summary = await script.upgrade(ctx)
            problems = await script.verify(ctx)
        except BaseException as e:
            await _record_failure(ledger, script.revision, label)
            if not isinstance(e, Exception):
                raise
            result.failed = script.revision
            return result

        if problems:
            recorded = problems[:_MAX_RECORDED_PROBLEMS]
            more = len(problems) - len(recorded)
            error = '\n'.join(
                [f'verify found {len(problems)} problem(s):', *recorded]
                + ([f'... and {more} more'] if more else [])
            )
            await ledger.mark_failed(script.revision, error)
            print(f'{label}: verify found {len(problems)} problem(s):')
            for problem in problems:
                print(f'  {problem}')
            result.failed = script.revision
            return result

        await ledger.mark_applied(script.revision, summary)
        applied.add(script.revision)
        result.applied.append(script.revision)
        print(f'{label}: applied')

    return result


async def run_downgrade(
    scripts: Sequence[AppMigrationScript],
    ledger: Any,
    ctx: Any,
    revision: str,
    *,
    applied_by: str = 'cli',
) -> RunResult:
    """Revert one migration and record it as `reverted`.

    Refused while a later migration that depends on it has run. A migration
    without `downgrade` cannot be reverted. Reverting one that has not run is
    a no-op, so a re-run after success is safe. With ``ctx.dry_run`` it
    reports what it would change and writes nothing to the ledger.
    """
    result = RunResult()
    script = next((s for s in scripts if s.revision == revision), None)
    if script is None:
        print(f'Unknown app migration revision {revision}')
        result.failed = revision
        return result

    label = f'{script.revision} ({script.description})'
    entries = await ledger.entries()
    # A failed run may have half applied (or half reverted) the change; the
    # downgrade is idempotent, so running it finishes the revert either way.
    ran = {
        rev
        for rev, entry in entries.items()
        if entry.status in (APPLIED, FAILED, RUNNING)
    }
    if revision not in ran:
        print(f'{label}: not applied; nothing to revert')
        return result
    if not script.reversible:
        print(f'{label}: is irreversible')
        result.failed = revision
        return result
    dependents = [s for s in scripts if revision in s.depends_on and s.revision in ran]
    if dependents:
        names = ', '.join(f'{s.revision} ({s.description})' for s in dependents)
        print(f'{label}: {names} depend on it and have run')
        result.failed = revision
        return result

    prefix = '[dry-run] ' if ctx.dry_run else ''
    print(f'{prefix}{label}: reverting')
    if ctx.dry_run:
        try:
            await script.downgrade(ctx)
        except Exception:
            print(traceback.format_exc())
            print(f'{prefix}{label}: failed')
            result.failed = revision
            return result
        result.reverted.append(revision)
        return result

    await ledger.mark_running(script.revision, script.description, applied_by)
    try:
        summary = await script.downgrade(ctx)
    except BaseException as e:
        await _record_failure(ledger, revision, label)
        if not isinstance(e, Exception):
            raise
        result.failed = revision
        return result

    await ledger.mark_reverted(revision, summary)
    result.reverted.append(revision)
    print(f'{label}: reverted')
    if script.applies(ctx.feature_flags):
        print(
            f'{label}: still applies with the current settings; the next '
            '`upgrade` applies it again'
            + (
                ', and floware will not start while it is pending'
                if script.blocking
                else ''
            )
        )
    return result


async def _record_failure(ledger: Any, revision: str, label: str) -> None:
    """Called from an except block: record and print the exception in flight.

    Ctrl-C and cancellation too, so the row says why the run stopped instead of
    staying `running`.
    """
    error = traceback.format_exc()
    try:
        await ledger.mark_failed(revision, error)
    except Exception:
        print(f'{label}: could not record the failure in the ledger')
    print(error)
    print(f'{label}: failed')


@asynccontextmanager
async def advisory_lock(db_client: DatabaseClient) -> AsyncIterator[None]:
    """Hold a session advisory lock so two runs never overlap on one database."""
    async with db_client.engine.connect() as connection:
        got = await connection.scalar(
            text('SELECT pg_try_advisory_lock(:key)'), {'key': ADVISORY_LOCK_KEY}
        )
        if not got:
            print('Another app-migration run holds the lock; waiting for it')
            await connection.execute(
                text('SELECT pg_advisory_lock(:key)'), {'key': ADVISORY_LOCK_KEY}
            )
        await connection.commit()
        try:
            yield
        finally:
            await connection.execute(
                text('SELECT pg_advisory_unlock(:key)'), {'key': ADVISORY_LOCK_KEY}
            )
            await connection.commit()


async def schema_heads(db_client: DatabaseClient) -> Tuple[set, set]:
    """(Alembic revisions the database is at, Alembic heads in this image)."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(
        Config(str(db_client._get_alembic_config_path()))
    )
    async with db_client.engine.connect() as connection:
        current = await connection.run_sync(
            lambda sync: MigrationContext.configure(sync).get_current_heads()
        )
    return set(current), set(script.get_heads())
