"""Ordering, gating and ledger bookkeeping of floware.app_migrations."""

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

from common_module.feature.feature_flag import FeatureFlags
from floware.app_migrations.ledger import (
    APPLIED,
    FAILED,
    REVERTED,
    RUNNING,
    LedgerEntry,
)
from floware.app_migrations.registry import (
    AppMigrationGraphError,
    AppMigrationScript,
    chain_head,
    load_migrations,
    order_chain,
)
from floware.app_migrations.runner import (
    NOT_APPLICABLE,
    PENDING,
    WAITING,
    migration_states,
    pending_blocking,
    run_downgrade,
    run_pending,
)
from floware.app_migrations.secret_conversion import ENCRYPT_MIGRATION_REVISION

FLAG_ON = FeatureFlags(envelope_encryption_enabled=True)
FLAG_OFF = FeatureFlags()


def script(
    revision: str,
    down_revision: Optional[str],
    *,
    calls: Optional[List[str]] = None,
    applies=None,
    blocking: bool = False,
    depends_on=(),
    problems: Optional[List[str]] = None,
    reversible: bool = True,
) -> AppMigrationScript:
    async def upgrade(ctx):
        if calls is not None:
            calls.append(f'{revision}{" dry" if ctx.dry_run else ""}')
        return {'ran': revision}

    async def verify(ctx):
        return list(problems or [])

    async def downgrade(ctx):
        if calls is not None:
            calls.append(f'-{revision}{" dry" if ctx.dry_run else ""}')
        return {'reverted': revision}

    module = SimpleNamespace(upgrade=upgrade, verify=verify)
    if reversible:
        module.downgrade = downgrade
    if applies is not None:
        module.applies = applies
    return AppMigrationScript(
        revision=revision,
        down_revision=down_revision,
        description=f'migration {revision}',
        blocking=blocking,
        depends_on=tuple(depends_on),
        path=Path(f'{revision}.py'),
        module=module,
    )


def entry(revision: str, status: str, error: Optional[str] = None) -> LedgerEntry:
    return LedgerEntry(revision, status, 'cli', None, None, error)


class FakeLedger:
    def __init__(self, rows: Optional[Dict[str, LedgerEntry]] = None):
        self.rows = dict(rows or {})
        self.summaries: Dict[str, dict] = {}
        self.writes = 0

    async def entries(self):
        return dict(self.rows)

    async def mark_running(self, revision, description, applied_by):
        self.writes += 1
        self.rows[revision] = entry(revision, RUNNING)

    async def mark_applied(self, revision, summary):
        self.writes += 1
        self.rows[revision] = entry(revision, APPLIED)
        self.summaries[revision] = summary

    async def mark_failed(self, revision, error):
        self.writes += 1
        self.rows[revision] = entry(revision, FAILED, error)

    async def mark_reverted(self, revision, summary):
        self.writes += 1
        self.rows[revision] = entry(revision, REVERTED)
        self.summaries[revision] = summary


def ctx(flags=FLAG_ON, dry_run=False):
    return SimpleNamespace(feature_flags=flags, dry_run=dry_run)


# ---- registry -------------------------------------------------------------


def test_order_follows_the_chain_not_the_input_order():
    scripts = [script('c', 'b'), script('a', None), script('b', 'a')]
    assert [s.revision for s in order_chain(scripts)] == ['a', 'b', 'c']


@pytest.mark.parametrize(
    'scripts, message',
    [
        ([script('a', None), script('a', None)], 'Duplicate'),
        ([script('a', None), script('b', 'x')], 'unknown revision x'),
        ([script('a', None), script('b', 'a'), script('c', 'a')], 'linear'),
        ([script('a', None), script('b', None)], 'linear'),
        (
            [script('a', None), script('b', 'a', depends_on=['c']), script('c', 'b')],
            'not an earlier revision',
        ),
    ],
)
def test_order_chain_rejects_invalid_graphs(scripts, message):
    with pytest.raises(AppMigrationGraphError, match=message):
        order_chain(scripts)


def test_load_migrations_reads_version_files(tmp_path):
    (tmp_path / '2026_01_01_0000-aaa_first.py').write_text(
        "revision = 'aaa'\ndown_revision = None\ndescription = 'first'\n"
        'async def upgrade(ctx):\n    return {}\n'
    )
    (tmp_path / '2026_01_02_0000-bbb_second.py').write_text(
        "revision = 'bbb'\ndown_revision = 'aaa'\ndescription = 'second'\n"
        "blocking = True\ndepends_on = ('aaa',)\n"
        'async def upgrade(ctx):\n    return {}\n'
    )
    (tmp_path / '_ignored.py').write_text('raise RuntimeError')

    scripts = load_migrations(tmp_path)

    assert [(s.revision, s.blocking, s.depends_on) for s in scripts] == [
        ('aaa', False, ()),
        ('bbb', True, ('aaa',)),
    ]


def test_load_migrations_rejects_a_description_too_long_for_the_ledger(tmp_path):
    (tmp_path / 'x.py').write_text(
        "revision = 'x'\ndown_revision = None\n"
        f"description = '{'d' * 256}'\n"
        'async def upgrade(ctx):\n    return {}\n'
    )
    with pytest.raises(AppMigrationGraphError, match='longer than 255'):
        load_migrations(tmp_path)


def test_chain_head_reads_files_without_importing_them(tmp_path):
    assert chain_head(tmp_path) is None
    (tmp_path / '1-aaa.py').write_text(
        "raise RuntimeError('imported')\nrevision = 'aaa'\ndown_revision = None\n"
    )
    (tmp_path / '2-bbb.py').write_text(
        "raise RuntimeError('imported')\nrevision = 'bbb'\ndown_revision = 'aaa'\n"
    )
    assert chain_head(tmp_path) == 'bbb'

    (tmp_path / '3-ccc.py').write_text("revision = 'ccc'\ndown_revision = 'aaa'\n")
    with pytest.raises(AppMigrationGraphError, match='one app migration head'):
        chain_head(tmp_path)


def test_load_migrations_rejects_sync_downgrade(tmp_path):
    (tmp_path / 'x.py').write_text(
        "revision = 'x'\ndown_revision = None\ndescription = 'x'\n"
        'async def upgrade(ctx):\n    return {}\n'
        'def downgrade(ctx):\n    return {}\n'
    )
    with pytest.raises(AppMigrationGraphError, match='`downgrade` must be async'):
        load_migrations(tmp_path)


def test_load_migrations_rejects_sync_upgrade(tmp_path):
    (tmp_path / 'x.py').write_text(
        "revision = 'x'\ndown_revision = None\ndescription = 'x'\n"
        'def upgrade(ctx):\n    return {}\n'
    )
    with pytest.raises(AppMigrationGraphError, match='must be async'):
        load_migrations(tmp_path)


def test_shipped_migrations_form_a_chain():
    scripts = load_migrations()
    encrypt = next(s for s in scripts if s.revision == ENCRYPT_MIGRATION_REVISION)
    assert encrypt.blocking
    assert encrypt.reversible
    assert encrypt.applies(FLAG_ON)
    assert not encrypt.applies(FLAG_OFF)


# ---- states ---------------------------------------------------------------


def test_states_cover_gating_dependencies_and_failures():
    scripts = [
        script('a', None, applies=lambda f: f.envelope_encryption_enabled),
        script('b', 'a'),
        script('c', 'b'),
        script('d', 'c', depends_on=['c']),
        script('e', 'd'),
    ]
    entries = {'b': entry('b', APPLIED), 'c': entry('c', FAILED, 'boom')}

    states = migration_states(scripts, entries, FLAG_OFF)

    assert [(s.script.revision, s.state, s.waiting_on) for s in states] == [
        ('a', NOT_APPLICABLE, ()),
        ('b', APPLIED, ()),
        ('c', FAILED, ()),
        ('d', WAITING, ('c',)),
        ('e', PENDING, ()),
    ]
    assert states[2].error == 'boom'


def test_depending_on_a_migration_that_does_not_apply_means_not_applicable():
    gated = lambda f: f.envelope_encryption_enabled  # noqa: E731
    scripts = [
        script('a', None, applies=gated),
        script('b', 'a', blocking=True, depends_on=['a']),
        script('c', 'b', depends_on=['b']),
    ]

    states = migration_states(scripts, {}, FLAG_OFF)

    assert [s.state for s in states] == [NOT_APPLICABLE] * 3
    # Waiting on it would keep floware from starting, forever.
    assert pending_blocking(scripts, {}, FLAG_OFF) == []
    # Once the dependency is applied, the flag no longer matters for it.
    assert [
        s.revision
        for s in pending_blocking(scripts, {'a': entry('a', APPLIED)}, FLAG_OFF)
    ] == ['b']


def test_pending_blocking_honours_flags():
    scripts = [
        script(
            'a', None, blocking=True, applies=lambda f: f.envelope_encryption_enabled
        ),
        script('b', 'a'),
    ]
    assert pending_blocking(scripts, {}, FLAG_OFF) == []
    assert [s.revision for s in pending_blocking(scripts, {}, FLAG_ON)] == ['a']
    assert pending_blocking(scripts, {'a': entry('a', APPLIED)}, FLAG_ON) == []
    # A failed or interrupted run still blocks.
    for status in (FAILED, RUNNING):
        blocked = pending_blocking(scripts, {'a': entry('a', status)}, FLAG_ON)
        assert [s.revision for s in blocked] == ['a']


# ---- run ------------------------------------------------------------------


async def test_runs_pending_in_order_and_skips_applied():
    calls: List[str] = []
    scripts = order_chain(
        [script('a', None, calls=calls), script('b', 'a', calls=calls)]
    )
    ledger = FakeLedger({'a': entry('a', APPLIED)})

    result = await run_pending(scripts, ledger, ctx())

    assert result.ok and result.applied == ['b']
    assert calls == ['b']
    assert ledger.rows['b'].status == APPLIED
    assert ledger.summaries['b'] == {'ran': 'b'}


async def test_not_applicable_stays_pending_and_later_ones_still_run():
    calls: List[str] = []
    scripts = [
        script('a', None, calls=calls, applies=lambda f: False),
        script('b', 'a', calls=calls),
    ]
    ledger = FakeLedger()

    result = await run_pending(scripts, ledger, ctx())

    assert result.ok and result.applied == ['b']
    assert calls == ['b']
    assert 'a' not in ledger.rows


async def test_dependent_waits_until_its_dependency_is_applied():
    calls: List[str] = []
    gate = {'on': False}
    scripts = [
        script('a', None, calls=calls, applies=lambda f: gate['on']),
        script('b', 'a', calls=calls, depends_on=['a']),
    ]
    ledger = FakeLedger()

    first = await run_pending(scripts, ledger, ctx())
    assert first.ok and first.applied == [] and calls == []

    gate['on'] = True
    second = await run_pending(scripts, ledger, ctx())
    # The dependency applied earlier in the same run counts.
    assert second.applied == ['a', 'b'] and calls == ['a', 'b']


async def test_failure_stops_the_run_and_a_retry_succeeds():
    calls: List[str] = []
    broken = {'fails': True}

    async def flaky(ctx):
        calls.append('a')
        if broken['fails']:
            raise RuntimeError('boom')
        return {}

    a = script('a', None)
    a.module.upgrade = flaky
    scripts = [a, script('b', 'a', calls=calls)]
    ledger = FakeLedger()

    result = await run_pending(scripts, ledger, ctx())
    assert result.failed == 'a' and calls == ['a']
    assert ledger.rows['a'].status == FAILED
    assert 'boom' in ledger.rows['a'].error

    broken['fails'] = False
    retry = await run_pending(scripts, ledger, ctx())
    assert retry.ok and retry.applied == ['a', 'b']


async def test_verify_problems_mark_the_migration_failed():
    scripts = [script('a', None, problems=['row 1 not encrypted'])]
    ledger = FakeLedger()

    result = await run_pending(scripts, ledger, ctx())

    assert result.failed == 'a'
    assert ledger.rows['a'].status == FAILED
    assert 'row 1 not encrypted' in ledger.rows['a'].error


async def test_dry_run_writes_nothing_to_the_ledger():
    calls: List[str] = []
    scripts = [
        script('a', None, calls=calls),
        script('b', 'a', calls=calls, depends_on=['a']),
    ]
    ledger = FakeLedger()

    result = await run_pending(scripts, ledger, ctx(dry_run=True))

    assert result.applied == ['a', 'b']
    assert calls == ['a dry', 'b dry']
    assert ledger.writes == 0


async def test_only_runs_one_revision_and_refuses_one_that_does_not_apply():
    calls: List[str] = []
    scripts = [
        script('a', None, calls=calls),
        script('b', 'a', calls=calls, applies=lambda f: False),
    ]

    result = await run_pending(scripts, FakeLedger(), ctx(), only='a')
    assert result.applied == ['a'] and calls == ['a']

    refused = await run_pending(scripts, FakeLedger(), ctx(), only='b')
    assert refused.failed == 'b'

    unknown = await run_pending(scripts, FakeLedger(), ctx(), only='zzz')
    assert unknown.failed == 'zzz'


async def test_dry_run_failure_is_reported_not_raised():
    a = script('a', None)

    async def broken(ctx):
        raise RuntimeError('boom')

    a.module.upgrade = broken
    ledger = FakeLedger()

    result = await run_pending([a, script('b', 'a')], ledger, ctx(dry_run=True))

    assert result.failed == 'a' and result.applied == []
    assert ledger.writes == 0


async def test_interrupted_run_is_recorded_failed_and_reraised():
    a = script('a', None)

    async def interrupted(ctx):
        raise KeyboardInterrupt

    a.module.upgrade = interrupted
    ledger = FakeLedger()

    with pytest.raises(KeyboardInterrupt):
        await run_pending([a], ledger, ctx())

    assert ledger.rows['a'].status == FAILED
    assert 'KeyboardInterrupt' in ledger.rows['a'].error


# ---- downgrade --------------------------------------------------------------


async def test_downgrade_reverts_and_the_migration_is_pending_again():
    calls: List[str] = []
    scripts = [script('a', None, calls=calls), script('b', 'a', calls=calls)]
    ledger = FakeLedger({'a': entry('a', APPLIED), 'b': entry('b', APPLIED)})

    result = await run_downgrade(scripts, ledger, ctx(), 'a')

    assert result.ok and result.reverted == ['a']
    assert calls == ['-a']  # b does not depend on a, so it stays applied
    assert ledger.rows['a'].status == REVERTED
    assert ledger.summaries['a'] == {'reverted': 'a'}

    states = migration_states(scripts, await ledger.entries(), FLAG_ON)
    assert [(s.state, s.reverted) for s in states] == [
        (PENDING, True),
        (APPLIED, False),
    ]

    again = await run_pending(scripts, ledger, ctx())
    assert again.applied == ['a'] and calls == ['-a', 'a']


def test_reverted_blocking_migration_that_still_applies_blocks_startup():
    gated = lambda f: f.envelope_encryption_enabled  # noqa: E731
    scripts = [script('a', None, blocking=True, applies=gated)]
    entries = {'a': entry('a', REVERTED)}

    assert [s.revision for s in pending_blocking(scripts, entries, FLAG_ON)] == ['a']
    assert pending_blocking(scripts, entries, FLAG_OFF) == []


async def test_downgrade_refuses_an_irreversible_migration():
    scripts = [script('a', None, reversible=False)]
    ledger = FakeLedger({'a': entry('a', APPLIED)})

    result = await run_downgrade(scripts, ledger, ctx(), 'a')

    assert result.failed == 'a'
    assert ledger.writes == 0


async def test_downgrade_refuses_while_a_dependent_has_run():
    calls: List[str] = []
    scripts = [
        script('a', None, calls=calls),
        script('b', 'a', calls=calls, depends_on=['a']),
    ]
    ledger = FakeLedger({'a': entry('a', APPLIED), 'b': entry('b', FAILED)})

    refused = await run_downgrade(scripts, ledger, ctx(), 'a')
    assert refused.failed == 'a' and calls == []

    assert (await run_downgrade(scripts, ledger, ctx(), 'b')).ok
    allowed = await run_downgrade(scripts, ledger, ctx(), 'a')
    assert allowed.reverted == ['a'] and calls == ['-b', '-a']


@pytest.mark.parametrize('rows', [{}, {'a': entry('a', REVERTED)}])
async def test_downgrading_what_has_not_run_is_a_no_op(rows):
    calls: List[str] = []
    ledger = FakeLedger(rows)

    result = await run_downgrade([script('a', None, calls=calls)], ledger, ctx(), 'a')

    assert result.ok and result.reverted == []
    assert calls == [] and ledger.writes == 0


async def test_downgrade_unknown_revision_fails():
    result = await run_downgrade([script('a', None)], FakeLedger(), ctx(), 'zzz')
    assert result.failed == 'zzz'


async def test_downgrade_dry_run_writes_nothing():
    calls: List[str] = []
    ledger = FakeLedger({'a': entry('a', APPLIED)})

    result = await run_downgrade(
        [script('a', None, calls=calls)], ledger, ctx(dry_run=True), 'a'
    )

    assert result.reverted == ['a'] and calls == ['-a dry']
    assert ledger.writes == 0 and ledger.rows['a'].status == APPLIED


async def test_downgrade_failure_is_recorded_and_a_retry_finishes():
    broken = {'fails': True}
    a = script('a', None)

    async def flaky(ctx):
        if broken['fails']:
            raise RuntimeError('boom')
        return {}

    a.module.downgrade = flaky
    ledger = FakeLedger({'a': entry('a', APPLIED)})

    failed = await run_downgrade([a], ledger, ctx(), 'a')
    assert failed.failed == 'a' and ledger.rows['a'].status == FAILED
    assert 'boom' in ledger.rows['a'].error

    broken['fails'] = False
    retry = await run_downgrade([a], ledger, ctx(), 'a')
    assert retry.ok and ledger.rows['a'].status == REVERTED


async def test_interrupted_downgrade_is_recorded_failed_and_reraised():
    a = script('a', None)

    async def interrupted(ctx):
        raise KeyboardInterrupt

    a.module.downgrade = interrupted
    ledger = FakeLedger({'a': entry('a', APPLIED)})

    with pytest.raises(KeyboardInterrupt):
        await run_downgrade([a], ledger, ctx(), 'a')

    assert ledger.rows['a'].status == FAILED
