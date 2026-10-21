"""Cancelling a pending execution: broker removal, the service rules, the route."""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from common_module.response_formatter import ResponseFormatter

from agents_module.controllers import async_inference_controller as controller
from agents_module.services import async_agentic_execution_service as svc_module
from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
    CancellationIncomplete,
    ExecutionNotCancellable,
)
from agents_module.utils.celery_broker import BrokerUnavailable, remove_queued_task
from agents_module.utils.celery_settings import CeleryProducerSettings

QUEUE = '{celery}'
SEP = '\x06\x16'


class _FakeChannel:
    priority_steps = [0, 3, 6, 9]

    def __init__(self, client):
        self._client = client

    def _q_for_pri(self, queue, pri):
        return f'{queue}{SEP}{pri}' if pri else queue

    @contextmanager
    def conn_or_acquire(self):
        yield self._client


def _app(eval_result=1):
    client = MagicMock()
    client.eval.return_value = eval_result
    conn = MagicMock()
    conn.default_channel = _FakeChannel(client)
    app = MagicMock()
    app.pool.acquire.return_value = conn
    app.pool.LimitExceeded = type('LimitExceeded', (Exception,), {})
    app.conf.task_default_queue = QUEUE
    return app, client, conn


# --- remove_queued_task ------------------------------------------------------
# The Lua script itself needs a real Redis; these cover what is sent to it.


def test_searches_every_priority_list_for_the_task_id():
    app, client, conn = _app(eval_result=1)

    assert remove_queued_task(app, 'task-1', CeleryProducerSettings()) is True

    _script, numkeys, *rest = client.eval.call_args.args
    keys, args = rest[:numkeys], rest[numkeys:]
    assert keys == [QUEUE, f'{QUEUE}{SEP}3', f'{QUEUE}{SEP}6', f'{QUEUE}{SEP}9']
    assert args == ['task-1']
    conn.release.assert_called_once()


def test_false_when_the_task_is_not_on_the_queue():
    app, _, conn = _app(eval_result=0)

    assert remove_queued_task(app, 'task-1', CeleryProducerSettings()) is False
    conn.release.assert_called_once()


def test_broker_errors_become_broker_unavailable():
    app, client, conn = _app()
    client.eval.side_effect = ConnectionError('redis down')

    with pytest.raises(BrokerUnavailable):
        remove_queued_task(app, 'task-1', CeleryProducerSettings())
    conn.release.assert_called_once()


def test_an_exhausted_pool_is_broker_unavailable():
    app, _, _ = _app()
    app.pool.acquire.side_effect = app.pool.LimitExceeded('full')

    with pytest.raises(BrokerUnavailable):
        remove_queued_task(app, 'task-1', CeleryProducerSettings())


# --- AsyncAgenticExecutionService.cancel_execution ----------------------------


def _record(**overrides):
    values = {
        'id': uuid.uuid4(),
        'status': 'pending',
        'celery_task_id': 'task-1',
        'input_bucket': 'bucket',
        'input_files': json.dumps([{'key': 'executions/x/inputs/0_a.pdf'}]),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _cancelled_row(record):
    row = MagicMock()
    row.to_dict.return_value = {
        'id': str(record.id),
        'entity_type': 'agent',
        'entity_id': str(uuid.uuid4()),
        'celery_task_id': record.celery_task_id,
        'status': 'cancelled',
        'input_files': record.input_files,
        'created_at': '2026-10-19T10:00:00',
        'completed_at': '2026-10-19T10:00:05',
    }
    return row


def _service(record):
    repo = MagicMock()
    repo.find_one = AsyncMock(return_value=record)
    repo.find_one_and_update = AsyncMock(
        return_value=_cancelled_row(record) if record else None
    )
    service = AsyncAgenticExecutionService(
        async_agentic_execution_repository=repo,
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        executions_bucket='bucket',
        celery_client=MagicMock(),
    )
    return service, repo


async def test_marks_cancelled_caches_it_and_keeps_inputs():
    record = _record()
    service, repo = _service(record)

    with patch.object(svc_module, 'remove_queued_task', return_value=True) as rm:
        result = await service.cancel_execution(record.id)

    assert rm.call_args.args[1] == 'task-1'
    filters = repo.find_one_and_update.call_args.args[0]
    update = repo.find_one_and_update.call_args.kwargs
    assert filters == {'id': record.id, 'status': 'pending'}
    assert update['status'] == 'cancelled'
    assert 'input_files' not in update
    assert result.status == 'cancelled'
    assert result.input_files == [{'key': 'executions/x/inputs/0_a.pdf'}]

    key, cached, ttl = service.cache.add.call_args.args
    assert key == f'async_agentic_exec:status:{record.id}'
    assert json.loads(cached)['status'] == 'cancelled'
    assert ttl == svc_module._STATUS_CACHE_TTL_TERMINAL
    service.cloud_storage.delete_file.assert_not_called()


async def test_missing_task_id_is_refused_without_touching_the_broker():
    record = _record(celery_task_id=None)
    service, repo = _service(record)

    with patch.object(svc_module, 'remove_queued_task') as rm:
        with pytest.raises(ExecutionNotCancellable):
            await service.cancel_execution(record.id)

    rm.assert_not_called()
    repo.find_one_and_update.assert_not_awaited()


async def test_missing_execution_is_a_value_error():
    service, _ = _service(None)

    with pytest.raises(ValueError):
        await service.cancel_execution(uuid.uuid4())


@pytest.mark.parametrize('status', ['in_progress', 'completed', 'failed', 'cancelled'])
async def test_non_pending_is_refused_without_touching_the_broker(status):
    record = _record(status=status)
    service, repo = _service(record)

    with patch.object(svc_module, 'remove_queued_task') as rm:
        with pytest.raises(ExecutionNotCancellable):
            await service.cancel_execution(record.id)

    rm.assert_not_called()
    repo.find_one_and_update.assert_not_awaited()


async def test_not_on_the_queue_leaves_the_row_alone():
    record = _record()
    service, repo = _service(record)

    with patch.object(svc_module, 'remove_queued_task', return_value=False):
        with pytest.raises(ExecutionNotCancellable):
            await service.cancel_execution(record.id)

    repo.find_one_and_update.assert_not_awaited()
    service.cache.add.assert_not_called()


async def test_broker_unavailable_changes_nothing():
    record = _record()
    service, repo = _service(record)

    with patch.object(
        svc_module, 'remove_queued_task', side_effect=BrokerUnavailable('down')
    ):
        with pytest.raises(BrokerUnavailable):
            await service.cancel_execution(record.id)

    repo.find_one_and_update.assert_not_awaited()


async def test_db_failure_after_removal_is_reported_as_incomplete():
    record = _record()
    service, repo = _service(record)
    repo.find_one_and_update.side_effect = RuntimeError('db down')

    with patch.object(svc_module, 'remove_queued_task', return_value=True):
        with pytest.raises(CancellationIncomplete):
            await service.cancel_execution(record.id)

    service.cache.add.assert_not_called()


async def test_cache_failure_does_not_fail_a_persisted_cancel():
    record = _record()
    service, _ = _service(record)
    service.cache.add.side_effect = ConnectionError('redis down')

    with patch.object(svc_module, 'remove_queued_task', return_value=True):
        result = await service.cancel_execution(record.id)

    assert result.status == 'cancelled'


async def test_status_read_cannot_overwrite_a_cancel_already_in_the_cache():
    record = _record()
    service, repo = _service(record)
    repo.find_one.return_value = _cancelled_row(record)
    service.cache.get_str.return_value = None

    await service.get_execution_status(record.id)

    assert service.cache.add.call_args.kwargs == {'nx': True}


async def test_row_no_longer_pending_after_removal_leaves_the_cache_alone():
    record = _record()
    service, repo = _service(record)
    repo.find_one_and_update.return_value = None

    with patch.object(svc_module, 'remove_queued_task', return_value=True):
        with pytest.raises(CancellationIncomplete):
            await service.cancel_execution(record.id)

    service.cache.add.assert_not_called()


# --- POST /v1/agentic-executions/{execution_id}/cancel ------------------------


def _request(session):
    req = MagicMock()
    req.state.session = session
    return req


CANCELLED_ID = uuid.uuid4()


def _ok_result():
    return SimpleNamespace(
        id=CANCELLED_ID,
        status='cancelled',
        completed_at=datetime(2026, 10, 20, 10, 0, 5),
        celery_task_id='task-1',
        variables={'secret': 'x'},
    )


@pytest.mark.parametrize(
    'side_effect, expected',
    [
        (None, 200),
        (ValueError('Execution not found'), 404),
        (ExecutionNotCancellable('picked up'), 409),
        (BrokerUnavailable('redis down'), 503),
        (CancellationIncomplete('removed, row not updated'), 500),
    ],
)
async def test_route_status_codes(side_effect, expected, monkeypatch):
    monkeypatch.setattr(controller, 'check_is_admin', AsyncMock(return_value=True))
    service = MagicMock()
    service.cancel_execution = AsyncMock(
        side_effect=side_effect, return_value=_ok_result()
    )

    response = await controller.cancel_execution(
        request=_request(session=SimpleNamespace(role_id='admin-role')),
        execution_id=uuid.uuid4(),
        async_agentic_execution_service=service,
        response_formatter=ResponseFormatter(),
    )

    assert response.status_code == expected


async def test_route_returns_only_the_cancel_fields(monkeypatch):
    monkeypatch.setattr(controller, 'check_is_admin', AsyncMock(return_value=True))
    service = MagicMock()
    service.cancel_execution = AsyncMock(return_value=_ok_result())

    response = await controller.cancel_execution(
        request=_request(session=SimpleNamespace(role_id='admin-role')),
        execution_id=CANCELLED_ID,
        async_agentic_execution_service=service,
        response_formatter=ResponseFormatter(),
    )

    assert json.loads(response.body)['data']['data'] == {
        'execution_id': str(CANCELLED_ID),
        'status': 'cancelled',
        'cancelled_at': '2026-10-20T10:00:05',
    }


@pytest.mark.parametrize(
    'session, is_admin',
    [
        (SimpleNamespace(role_id='user-role'), False),
        (None, True),  # no session never reaches the role check
    ],
)
async def test_route_refuses_non_admins(session, is_admin, monkeypatch):
    monkeypatch.setattr(controller, 'check_is_admin', AsyncMock(return_value=is_admin))
    service = MagicMock()
    service.cancel_execution = AsyncMock()

    response = await controller.cancel_execution(
        request=_request(session),
        execution_id=uuid.uuid4(),
        async_agentic_execution_service=service,
        response_formatter=ResponseFormatter(),
    )

    assert response.status_code == 403
    service.cancel_execution.assert_not_awaited()
