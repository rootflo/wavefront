"""A refused enqueue must upload nothing and insert no row."""

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents_module.services import async_agentic_execution_service as module
from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
)
from agents_module.utils.celery_backpressure import QueueBackpressure


@pytest.fixture
def uuid4():
    return uuid.uuid4()


@pytest.fixture
def service():
    svc = AsyncAgenticExecutionService(
        async_agentic_execution_repository=MagicMock(),
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        celery_client=MagicMock(),
        executions_bucket='test-bucket',
    )
    svc.repo.create = AsyncMock()
    svc.repo.find_one_and_update = AsyncMock()
    return svc


@pytest.fixture
def saturated():
    """The queue is over its limit."""
    with patch.object(
        module,
        'ensure_queue_capacity',
        AsyncMock(side_effect=QueueBackpressure(10000, 10000)),
    ) as guard:
        yield guard


@pytest.fixture
def has_capacity():
    with patch.object(module, 'ensure_queue_capacity', AsyncMock()) as guard:
        yield guard


# A binary input; a plain string never reaches cloud storage.
PDF_B64 = base64.b64encode(b'%PDF-1.4 fake').decode('utf-8')

BINARY_INPUTS = [
    {
        'role': 'user',
        'content': {
            'document_base64': PDF_B64,
            'mime_type': 'application/pdf',
            'file_name': 'doc.pdf',
        },
    }
]

AGENT_KWARGS = dict(
    inputs=BINARY_INPUTS,
    variables=None,
    output_json_enabled=False,
    access_token=None,
    app_key=None,
)

WORKFLOW_KWARGS = dict(
    workflow_name='wf',
    namespace='default',
    inputs=BINARY_INPUTS,
    variables=None,
    output_json_enabled=False,
    access_token=None,
    app_key=None,
)


async def test_agent_enqueue_refused_when_saturated(service, saturated, uuid4):
    with pytest.raises(QueueBackpressure):
        await service.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)


async def test_agent_refusal_writes_no_blob_and_no_row(service, saturated, uuid4):
    with pytest.raises(QueueBackpressure):
        await service.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)

    service.cloud_storage.save_small_file.assert_not_called()
    service.repo.create.assert_not_called()
    service.repo.find_one_and_update.assert_not_called()


async def test_workflow_refusal_writes_no_blob_and_no_row(service, saturated, uuid4):
    with pytest.raises(QueueBackpressure):
        await service.create_and_enqueue_workflow(workflow_id=uuid4, **WORKFLOW_KWARGS)

    service.cloud_storage.save_small_file.assert_not_called()
    service.repo.create.assert_not_called()


async def test_refusal_is_not_a_value_error(service, saturated, uuid4):
    """The controllers map ValueError to 422; this must not land there."""
    with pytest.raises(QueueBackpressure) as exc_info:
        await service.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)

    assert not isinstance(exc_info.value, ValueError)


async def test_worker_internal_callers_skip_the_guard(service, saturated, uuid4):
    """Inside the worker a refusal would lose already-admitted work."""
    service.celery.send_task.return_value.id = 'task-1'

    await service.create_and_enqueue_agent(
        agent_id=uuid4, enforce_queue_limit=False, **AGENT_KWARGS
    )

    saturated.assert_not_called()
    service.repo.create.assert_called_once()


async def test_enqueue_proceeds_when_there_is_capacity(service, has_capacity, uuid4):
    service.celery.send_task.return_value.id = 'task-1'

    result = await service.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)

    has_capacity.assert_awaited_once()
    service.cloud_storage.save_small_file.assert_called_once()
    service.repo.create.assert_called_once()
    assert result.status == 'pending'


@pytest.mark.parametrize('entity', ['agent', 'workflow'])
async def test_task_id_is_saved_with_the_row_and_sent_as_is(
    service, has_capacity, uuid4, entity
):
    if entity == 'agent':
        await service.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)
    else:
        await service.create_and_enqueue_workflow(workflow_id=uuid4, **WORKFLOW_KWARGS)

    row = service.repo.create.call_args.kwargs
    sent_task_id = service.celery.send_task.call_args.kwargs['task_id']
    assert row['celery_task_id'] == sent_task_id
    assert sent_task_id != str(row['id'])
    service.repo.find_one_and_update.assert_not_awaited()


async def test_service_passes_its_configured_settings_to_the_gate(uuid4):
    """The limit that applies is the one from config.ini, not a default."""
    from agents_module.utils.celery_settings import CeleryProducerSettings

    settings = CeleryProducerSettings(max_queue_depth='7')
    svc = AsyncAgenticExecutionService(
        async_agentic_execution_repository=MagicMock(),
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        celery_client=MagicMock(),
        executions_bucket='test-bucket',
        celery_settings=settings,
    )

    with patch.object(
        module, 'queue_is_saturated', AsyncMock(return_value=(True, 7))
    ) as predicate:
        assert await svc.queue_is_saturated() is True
    predicate.assert_awaited_once_with(svc.celery, settings)

    with patch.object(module, 'ensure_queue_capacity', AsyncMock()) as guard:
        svc.repo.create = AsyncMock()
        svc.repo.find_one_and_update = AsyncMock()
        await svc.create_and_enqueue_agent(agent_id=uuid4, **AGENT_KWARGS)
    guard.assert_awaited_once_with(svc.celery, settings)
