"""Tests for the datasource -> notification feed fan-out.

The feed sits one step further down the best-effort chain than the audit trail:
it runs after a mutation that has already committed *and* after an audit row that
has already landed. So the behaviours that matter are that it is off unless
explicitly enabled, that it never costs an audit row, and that what it publishes
is a faithful copy of what was audited rather than a second, drifting capture.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from common_module.feature.feature_flag import (
    DATASOURCE_CHANGE_NOTIFICATION_FLAG,
    feature_flag_config,
)
from plugins_module.services.change_notification_service import (
    NOTIFICATION_TYPE,
    ChangeNotificationService,
)
from plugins_module.services.datasource_audit_service import (
    AuditActor,
    AuditEntry,
    DatasourceAuditService,
)

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
ACTOR = AuditActor(user_id='actor-user', role_id='actor-role', request_id='req-1')
OCCURRED_AT = datetime(2026, 9, 8, 12, 0, 0)


@pytest.fixture
def flag_on():
    """Enable the feature for one test.

    Patches the dict rather than os.environ: feature_flag_config is populated at
    import time, so setting the environment variable here would have no effect.
    """
    previous = feature_flag_config[DATASOURCE_CHANGE_NOTIFICATION_FLAG]
    feature_flag_config[DATASOURCE_CHANGE_NOTIFICATION_FLAG] = 'true'
    yield
    feature_flag_config[DATASOURCE_CHANGE_NOTIFICATION_FLAG] = previous


@pytest.fixture
def audit_repository():
    repo = MagicMock()
    repo.create_all = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def notification_repository():
    repo = MagicMock()
    repo.create = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def notifications(notification_repository):
    return ChangeNotificationService(notification_repository=notification_repository)


@pytest.fixture
def service(audit_repository, notifications):
    return DatasourceAuditService(
        audit_log_repository=audit_repository,
        change_notification_service=notifications,
    )


def _entry(**overrides):
    defaults = dict(
        table_name='orders',
        snapshot='after',
        rows=[{'id': 'r-1', 'status': 'shipped'}],
        before_rows=[{'id': 'r-1', 'status': 'pending'}],
        key_columns=['id'],
        rows_affected=1,
        filter="id eq 'r-1'",
        filter_params={'id': 'r-1'},
        meta={'multi_table': False, 'patch': {'status': 'shipped'}},
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


async def _record(service, entries, operation='update'):
    await service.record(
        datasource_id=DATASOURCE_ID,
        datasource_type='postgres',
        operation=operation,
        entries=entries,
        actor=ACTOR,
        occurred_at=OCCURRED_AT,
    )


def _published(notification_repository):
    """The kwargs of the single notification row that was written."""
    assert notification_repository.create.await_count == 1
    return notification_repository.create.await_args.kwargs


class TestFeatureFlag:
    async def test_disabled_by_default_writes_no_notification(
        self, service, audit_repository, notification_repository
    ):
        await _record(service, [_entry()])

        # The audit trail is unaffected by the flag; only the feed is gated.
        assert audit_repository.create_all.await_count == 1
        notification_repository.create.assert_not_awaited()

    async def test_enabled_writes_one_notification(
        self, service, audit_repository, notification_repository, flag_on
    ):
        await _record(service, [_entry()])

        assert audit_repository.create_all.await_count == 1
        assert notification_repository.create.await_count == 1

    async def test_audit_service_without_notification_service_still_records(
        self, audit_repository, flag_on
    ):
        # The dependency is optional; audit-only construction must keep working.
        service = DatasourceAuditService(audit_log_repository=audit_repository)

        await _record(service, [_entry()])

        assert audit_repository.create_all.await_count == 1


class TestPayload:
    async def test_one_notification_per_batch_not_per_table(
        self, service, notification_repository, flag_on
    ):
        await _record(
            service,
            [_entry(table_name='orders'), _entry(table_name='line_items')],
        )

        data = _published(notification_repository)['data']
        assert data['table_count'] == 2
        assert [t['table_name'] for t in data['tables']] == ['orders', 'line_items']

    async def test_batch_id_matches_the_audit_rows(
        self, service, audit_repository, notification_repository, flag_on
    ):
        await _record(service, [_entry()])

        records = audit_repository.create_all.await_args.args[0]
        data = _published(notification_repository)['data']
        assert data['batch_id'] == str(records[0].batch_id)

    async def test_payload_is_identical_to_the_audit_row(
        self, service, audit_repository, notification_repository, flag_on
    ):
        await _record(service, [_entry()])

        record = audit_repository.create_all.await_args.args[0][0]
        table = _published(notification_repository)['data']['tables'][0]

        # Copied, not recaptured: the feed and the trail must never be able to
        # disagree about what changed.
        assert table['changes'] == record.changes
        assert table['meta'] == record.meta
        assert table['filter_params'] == record.filter_params
        assert table['filter'] == record.filter
        assert table['rows_affected'] == record.rows_affected

    async def test_envelope_fields(self, service, notification_repository, flag_on):
        await _record(service, [_entry()])

        published = _published(notification_repository)
        data = published['data']

        assert published['type'] == NOTIFICATION_TYPE
        assert data['source'] == 'datasource'
        assert data['datasource_id'] == DATASOURCE_ID
        assert data['datasource_type'] == 'postgres'
        assert data['operation'] == 'update'
        assert data['occurred_at'] == OCCURRED_AT.isoformat()
        assert data['actor'] == {
            'user_id': 'actor-user',
            'role_id': 'actor-role',
            'request_id': 'req-1',
        }

    async def test_update_carries_patch_and_diff(
        self, service, notification_repository, flag_on
    ):
        await _record(service, [_entry()])

        table = _published(notification_repository)['data']['tables'][0]
        assert table['meta']['patch'] == {'status': 'shipped'}
        assert table['changes']['snapshot'] == 'diff'
        assert table['changes']['rows'][0]['before'] == {'status': 'pending'}
        assert table['changes']['rows'][0]['after'] == {'status': 'shipped'}

    async def test_delete_carries_the_whole_prior_row(
        self, service, notification_repository, flag_on
    ):
        await _record(
            service,
            [
                _entry(
                    snapshot='deleted',
                    rows=[{'id': 'r-1', 'status': 'pending'}],
                    before_rows=None,
                    meta={'multi_table': False},
                )
            ],
            operation='delete',
        )

        table = _published(notification_repository)['data']['tables'][0]
        assert table['changes']['snapshot'] == 'deleted'
        assert table['changes']['rows'] == [{'id': 'r-1', 'status': 'pending'}]

    async def test_capture_unavailable_is_null_changes_with_a_reason(
        self, service, notification_repository, flag_on
    ):
        await _record(service, [_entry(rows=None, before_rows=None)])

        table = _published(notification_repository)['data']['tables'][0]
        # Null, not []: "no capture was available" is not "touched nothing".
        assert table['changes'] is None
        assert table['meta']['truncation_reason'] == 'capture_unavailable'

    async def test_rows_affected_is_the_uncapped_total(
        self, service, notification_repository, flag_on
    ):
        await _record(
            service,
            [
                _entry(table_name='orders', rows_affected=5000),
                _entry(table_name='line_items', rows_affected=3),
            ],
        )

        data = _published(notification_repository)['data']
        assert data['rows_affected'] == 5003

    async def test_zero_row_mutation_publishes_nothing(
        self, service, audit_repository, notification_repository, flag_on
    ):
        await _record(service, [_entry(rows_affected=0)])

        audit_repository.create_all.assert_not_awaited()
        notification_repository.create.assert_not_awaited()


class TestBatchCap:
    async def test_trailing_changes_dropped_when_the_batch_is_too_large(
        self, audit_repository, notification_repository, flag_on
    ):
        # Sized so shedding the trailing table's `changes` alone gets under it,
        # isolating step 1 from the rest of the ladder.
        notifications = ChangeNotificationService(
            notification_repository=notification_repository,
            max_payload_bytes=1_500,
        )
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        wide = [{'id': f'r-{i}', 'blob': 'x' * 200} for i in range(3)]
        await _record(
            service,
            [
                _entry(table_name='orders', rows=wide, before_rows=None),
                _entry(table_name='line_items', rows=wide, before_rows=None),
            ],
        )

        data = _published(notification_repository)['data']
        assert data['truncation_reason'] == 'batch_size_cap'
        # Front to back: the entries a feed shows first keep their detail.
        assert data['tables'][0]['changes'] is not None
        assert data['tables'][-1]['changes'] is None
        # Nothing cheaper had to go, so the metadata is intact and the
        # notification still reports that the table changed and by how much.
        assert data.get('metadata_dropped') is None
        assert data['tables'][-1]['table_name'] == 'line_items'
        assert data['tables'][-1]['rows_affected'] == 1

    async def test_leading_table_changes_outlive_the_uncapped_metadata(
        self, audit_repository, notification_repository, flag_on
    ):
        """Ordering guarantee: detail is shed after the uncapped fields.

        The leading table's `changes` is the last thing a reader can still act
        on, and it is already bounded by the audit service's per-table cap.
        `meta` and `filter_params` are bounded by nothing, so they go first.
        """
        # Big enough that dropping the uncapped fields suffices, small enough
        # that something has to go.
        notifications = ChangeNotificationService(
            notification_repository=notification_repository, max_payload_bytes=800
        )
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(
            service,
            [_entry(table_name='orders'), _entry(table_name='line_items')],
        )

        data = _published(notification_repository)['data']
        assert data['metadata_dropped'] is True
        assert all(t['meta'] is None for t in data['tables'])
        # Detail survived the metadata.
        assert data['tables'][0]['changes'] is not None

    async def test_leading_table_changes_go_last_when_nothing_else_is_left(
        self, audit_repository, notification_repository, flag_on
    ):
        # Below what the metadata drop alone can achieve, so step 3 has to run.
        notifications = ChangeNotificationService(
            notification_repository=notification_repository, max_payload_bytes=700
        )
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(
            service,
            [_entry(table_name='orders'), _entry(table_name='line_items')],
        )

        data = _published(notification_repository)['data']
        assert ChangeNotificationService._encoded_size(data) <= 700
        assert data['tables'][0]['changes'] is None
        # The tables themselves are still reported; only their detail is gone.
        assert [t['table_name'] for t in data['tables']] == ['orders', 'line_items']

    async def test_budget_is_enforced_when_the_bloat_is_uncapped_metadata(
        self, audit_repository, notification_repository, flag_on
    ):
        """`changes` is not the only thing that can overflow.

        meta.patch is copied through uncapped, so a document can exceed the
        budget with every `changes` already empty -- in which case dropping
        detail frees nothing and only `meta` will do.
        """
        budget = 50_000
        notifications = ChangeNotificationService(
            notification_repository=notification_repository,
            max_payload_bytes=budget,
        )
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(
            service,
            [
                _entry(
                    table_name=f't{i}',
                    rows=[],
                    before_rows=None,
                    meta={'patch': {'col': 'y' * 40000}},
                    filter_params={'id': f'r-{i}'},
                )
                for i in range(4)
            ],
        )

        published = _published(notification_repository)['data']
        assert ChangeNotificationService._encoded_size(published) <= budget
        assert published['metadata_dropped'] is True
        assert published['truncation_reason'] == 'batch_size_cap'
        assert all(t['meta'] is None for t in published['tables'])
        # Which rows were targeted survives dropping what they became.
        assert [t['filter_params'] for t in published['tables']] == [
            {'id': f'r-{i}'} for i in range(4)
        ]

    async def test_filter_params_is_never_dropped(
        self, audit_repository, notification_repository, flag_on
    ):
        """Identity outlives detail, at every level of trimming.

        filter_params says which rows were targeted. `filter` carries the same
        thing but is clipped to 512 characters, so nothing else here recovers
        it -- unlike meta.patch, which changes.after duplicates.
        """
        for budget in (1, 200, 700, 800, 1_500):
            notification_repository.create.reset_mock()
            notifications = ChangeNotificationService(
                notification_repository=notification_repository,
                max_payload_bytes=budget,
            )
            service = DatasourceAuditService(
                audit_log_repository=audit_repository,
                change_notification_service=notifications,
            )

            await _record(
                service,
                [
                    _entry(table_name='orders', filter_params={'id': 'r-1'}),
                    _entry(table_name='line_items', filter_params={'id': 'r-2'}),
                ],
            )

            published = _published(notification_repository)['data']
            # Whatever else went, every table still present says which rows it
            # touched.
            assert all(
                t['filter_params'] is not None for t in published['tables']
            ), budget

    @pytest.mark.parametrize('budget', [1, 200, 2_000, 50_000])
    async def test_never_published_over_budget(
        self, audit_repository, notification_repository, flag_on, budget
    ):
        """The invariant, across budgets no trimming step alone can satisfy."""
        notifications = ChangeNotificationService(
            notification_repository=notification_repository,
            max_payload_bytes=budget,
        )
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(
            service,
            [
                _entry(
                    table_name=f'table_{i}' * 20,
                    rows=[{'id': f'r-{i}', 'blob': 'x' * 5000}],
                    before_rows=None,
                    meta={'patch': {'col': 'y' * 5000}},
                )
                for i in range(12)
            ],
        )

        published = _published(notification_repository)['data']
        size = ChangeNotificationService._encoded_size(published)
        # A budget below the size of the envelope alone is unsatisfiable; the
        # document must still be trimmed as far as it can go.
        assert published['truncation_reason'] == 'batch_size_cap'
        if budget >= 2_000:
            assert size <= budget, (budget, size)
        assert len(published['tables']) >= 1

    async def test_single_table_at_the_per_table_cap_keeps_its_changes(
        self, service, notification_repository, flag_on
    ):
        """The batch budget must exceed the per-table budget.

        A table whose rows sit just under AUDIT_MAX_PAYLOAD_BYTES is legal and is
        kept in full by the audit row. When the batch budget was that same
        number, the envelope around it pushed the document over and `changes`
        was dropped entirely -- detail present in the trail, absent from the feed.
        """
        rows = [{'id': f'r-{i}', 'blob': 'x' * 13070} for i in range(20)]
        await _record(
            service,
            [
                _entry(
                    table_name='orders',
                    snapshot='deleted',
                    rows=rows,
                    before_rows=None,
                    rows_affected=20,
                )
            ],
            operation='delete',
        )

        data = _published(notification_repository)['data']
        assert data['tables'][0]['changes'] is not None
        assert len(data['tables'][0]['changes']['rows']) == 20
        assert 'truncation_reason' not in data


class TestTitle:
    @pytest.mark.parametrize(
        'operation,rows_affected,expected',
        [
            ('update', 3, '3 rows updated in orders'),
            ('update', 1, '1 row updated in orders'),
            ('delete', 1, '1 row deleted from orders'),
            ('insert', 12, '12 rows inserted into orders'),
        ],
    )
    async def test_single_table(
        self,
        service,
        notification_repository,
        flag_on,
        operation,
        rows_affected,
        expected,
    ):
        await _record(
            service, [_entry(rows_affected=rows_affected)], operation=operation
        )

        assert _published(notification_repository)['title'] == expected

    async def test_multi_table_counts_tables(
        self, service, notification_repository, flag_on
    ):
        await _record(
            service,
            [
                _entry(table_name='orders', rows_affected=4),
                _entry(table_name='line_items', rows_affected=3),
            ],
        )

        # Not "updated in across 2 tables" -- the preposition belongs only to the
        # single-table form.
        assert _published(notification_repository)['title'] == (
            '7 rows updated across 2 tables'
        )

    async def test_long_table_name_is_clipped(
        self, service, notification_repository, flag_on
    ):
        await _record(service, [_entry(table_name='t' * 200)])

        title = _published(notification_repository)['title']
        assert title.endswith('…')
        assert len(title) < 100

    async def test_unknown_operation_falls_back_instead_of_raising(
        self, service, notification_repository, flag_on
    ):
        await _record(service, [_entry()], operation='upsert')

        assert _published(notification_repository)['title'] == (
            '1 row changed (upsert) in orders'
        )


class TestBestEffort:
    async def test_publish_failure_leaves_the_audit_rows_written(
        self, service, audit_repository, notification_repository, flag_on
    ):
        notification_repository.create.side_effect = RuntimeError('db down')

        await _record(service, [_entry()])

        assert audit_repository.create_all.await_count == 1

    async def test_build_failure_does_not_cost_the_audit_row(
        self, audit_repository, notifications, flag_on
    ):
        notifications.build_payload = MagicMock(side_effect=RuntimeError('boom'))
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(service, [_entry()])

        # The build runs before the insert, so a bug there must not be what
        # stops the trail from being written.
        assert audit_repository.create_all.await_count == 1

    async def test_payload_is_built_before_the_audit_commit(
        self, notification_repository, notifications, flag_on
    ):
        """Guards the expire_on_commit hazard.

        create_all commits and closes its session, which expires and detaches
        the records. This fake stands in for that: it blanks the attributes the
        payload reads. If the payload were built afterwards, `changes` would come
        back None.
        """
        audit_repository = MagicMock()

        async def _expire(records, *args, **kwargs):
            for record in records:
                record.changes = None
                record.meta = None
            return records

        audit_repository.create_all = AsyncMock(side_effect=_expire)
        service = DatasourceAuditService(
            audit_log_repository=audit_repository,
            change_notification_service=notifications,
        )

        await _record(service, [_entry()])

        table = _published(notification_repository)['data']['tables'][0]
        assert table['changes'] is not None
        assert table['changes']['snapshot'] == 'diff'

    async def test_audit_write_failure_publishes_nothing(
        self, service, audit_repository, notification_repository, flag_on
    ):
        audit_repository.create_all.side_effect = RuntimeError('db down')

        await _record(service, [_entry()])

        # The trail is the record of truth; a feed entry for a change with no
        # audit row would claim more than was recorded.
        notification_repository.create.assert_not_awaited()


class TestUuidHandling:
    async def test_batch_id_is_serialized_as_a_string(
        self, service, notification_repository, flag_on
    ):
        await _record(service, [_entry()])

        data = _published(notification_repository)['data']
        # jsonb takes no UUID objects; a raw one would fail the insert.
        assert isinstance(data['batch_id'], str)
        uuid.UUID(data['batch_id'])
