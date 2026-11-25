from unittest.mock import AsyncMock, MagicMock

import pytest

from floware.services.scheduled_job_service import ScheduledJobService


def _service(results_by_query_id):
    """A ScheduledJobService with only what the scheduled_query path touches."""
    service = ScheduledJobService.__new__(ScheduledJobService)
    service.dynamic_query_service = MagicMock()
    service.dynamic_query_service.get_dynamic_yaml_query = AsyncMock(
        side_effect=lambda query_id: ([{'id': query_id}], query_id)
    )

    plugin = MagicMock()

    async def execute(yaml_query, rls, filter_expr, offset, limit, params):
        outcome = results_by_query_id[yaml_query[0]['id']]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    plugin.execute_dynamic_query = AsyncMock(side_effect=execute)
    service._get_datasource_plugin = AsyncMock(return_value=(plugin, 'pg', 'ds-1'))
    service._validate_email_connection = AsyncMock()
    return service, plugin


def _ok(rows):
    return {'q': {'status': 'success', 'result': rows}}


async def test_runs_every_query_without_rls_and_discards_rows():
    service, plugin = _service({'a': _ok([{'x': 1}]), 'b': _ok([])})
    payload = {
        'datasource_id': 'ds-1',
        'queries': [{'query_id': 'a', 'limit': 5}, {'query_id': 'b'}],
    }

    await service._execute_scheduled_query_job(payload, 'UTC')

    assert plugin.execute_dynamic_query.await_count == 2
    first_call = plugin.execute_dynamic_query.await_args_list[0].args
    assert first_call[1] is None  # no RLS filter
    assert first_call[4] == 5  # per-query limit applied


async def test_one_failing_query_fails_the_run_but_others_still_run():
    service, plugin = _service({'a': RuntimeError('boom'), 'b': _ok([{'x': 1}])})
    payload = {
        'datasource_id': 'ds-1',
        'queries': [{'query_id': 'a'}, {'query_id': 'b'}],
    }

    with pytest.raises(ValueError, match='1/2 queries: a'):
        await service._execute_scheduled_query_job(payload, 'UTC')
    assert plugin.execute_dynamic_query.await_count == 2


async def test_validate_payload_skips_email_checks_for_scheduled_query():
    service, _ = _service({})
    await service._validate_payload(
        'scheduled_query', {'datasource_id': 'ds-1', 'queries': [{'query_id': 'a'}]}
    )
    service._validate_email_connection.assert_not_awaited()

    await service._validate_payload(
        'email_dynamic_query',
        {'datasource_id': 'ds-1', 'queries': [{'query_id': 'a'}]},
    )
    service._validate_email_connection.assert_awaited_once()


@pytest.mark.parametrize(
    'job_type, payload, message',
    [
        ('scheduled_query', {'datasource_id': 'ds-1', 'queries': []}, 'non-empty'),
        ('scheduled_query', {'queries': [{'query_id': 'a'}]}, 'datasource_id'),
        ('nope', {'datasource_id': 'ds-1', 'queries': [{'query_id': 'a'}]}, 'job_type'),
    ],
)
async def test_validate_payload_rejects_bad_payloads(job_type, payload, message):
    service, _ = _service({})
    with pytest.raises(ValueError, match=message):
        await service._validate_payload(job_type, payload)
