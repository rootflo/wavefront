"""Retrying a failed execution: the service rules, the enqueue, the route."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from common_module.response_formatter import ResponseFormatter
from sqlalchemy.exc import IntegrityError

from agents_module.controllers import async_inference_controller as controller
from agents_module.services import async_agentic_execution_service as svc_module
from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
    ExecutionNotRetryable,
)
from agents_module.utils.celery_backpressure import QueueBackpressure
from agents_module.utils.celery_settings import CeleryProducerSettings

STORED_INPUTS = [
    {'role': 'user', 'content': 'summarise this'},
    {
        'role': 'user',
        'stored': True,
        'bucket': 'bucket',
        'key': 'executions/agents/a/parent/inputs/0_doc.pdf',
        'file_name': 'doc.pdf',
        'mime_type': 'application/pdf',
        'input_type': 'document',
    },
]
STORED_FILES = [
    {
        'key': 'executions/agents/a/parent/inputs/0_doc.pdf',
        'file_name': 'doc.pdf',
        'mime_type': 'application/pdf',
        'input_type': 'document',
    }
]


def _parent(**overrides):
    values = {
        'id': uuid.uuid4(),
        'entity_type': 'agent',
        'entity_id': uuid.uuid4(),
        'status': 'failed',
        'inputs': json.dumps(STORED_INPUTS),
        'input_files': json.dumps(STORED_FILES),
        'variables': {'customer_id': 'c-1'},
        'version': 2,
        'output_json_enabled': True,
        'llm_inference_config_id': uuid.uuid4(),
        'retry_of_execution_id': None,
        'attempt': 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(parent, existing_retry=None, max_attempts=3):
    repo = MagicMock()

    async def find_one(**filters):
        if 'retry_of_execution_id' in filters:
            return existing_retry
        return parent

    repo.find_one = AsyncMock(side_effect=find_one)
    repo.create = AsyncMock()
    repo.find_one_and_update = AsyncMock()
    service = AsyncAgenticExecutionService(
        async_agentic_execution_repository=repo,
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        executions_bucket='bucket',
        celery_client=MagicMock(),
        celery_settings=CeleryProducerSettings(max_execution_attempts=max_attempts),
    )
    return service, repo


@pytest.fixture
def has_capacity():
    with patch.object(svc_module, 'ensure_queue_capacity', AsyncMock()) as guard:
        yield guard


# --- get_retryable_execution ---------------------------------------------------


async def test_failed_execution_is_retryable():
    parent = _parent()
    service, _ = _service(parent)

    assert await service.get_retryable_execution(parent.id) is parent


async def test_missing_execution_is_a_value_error():
    service, _ = _service(None)

    with pytest.raises(ValueError):
        await service.get_retryable_execution(uuid.uuid4())


@pytest.mark.parametrize('status', ['pending', 'in_progress', 'completed', 'cancelled'])
async def test_only_failed_executions_are_retryable(status):
    parent = _parent(status=status)
    service, _ = _service(parent)

    with pytest.raises(ExecutionNotRetryable):
        await service.get_retryable_execution(parent.id)


async def test_an_already_retried_execution_is_refused():
    parent = _parent()
    service, _ = _service(parent, existing_retry=SimpleNamespace(id=uuid.uuid4()))

    with pytest.raises(ExecutionNotRetryable, match='already retried'):
        await service.get_retryable_execution(parent.id)


async def test_the_attempt_cap_is_enforced():
    parent = _parent(attempt=3, retry_of_execution_id=uuid.uuid4())
    service, _ = _service(parent, max_attempts=3)

    with pytest.raises(ExecutionNotRetryable, match='attempt 3 of at most 3'):
        await service.get_retryable_execution(parent.id)


async def test_a_cap_of_one_disables_retries():
    parent = _parent()
    service, _ = _service(parent, max_attempts=1)

    with pytest.raises(ExecutionNotRetryable):
        await service.get_retryable_execution(parent.id)


async def test_a_row_without_inputs_is_refused():
    parent = _parent(inputs=None)
    service, _ = _service(parent)

    with pytest.raises(ExecutionNotRetryable):
        await service.get_retryable_execution(parent.id)


# --- retry_execution -------------------------------------------------------------


async def test_agent_retry_reuses_inputs_and_links_back(has_capacity):
    parent = _parent()
    service, repo = _service(parent)

    result = await service.retry_execution(
        parent, access_token='tok', app_key=None, version=5
    )

    row = repo.create.call_args.kwargs
    assert row['entity_type'] == 'agent'
    assert row['entity_id'] == parent.entity_id
    assert json.loads(row['inputs']) == STORED_INPUTS
    assert json.loads(row['input_files']) == STORED_FILES
    assert row['variables'] == parent.variables
    assert row['version'] == 5
    assert row['output_json_enabled'] is True
    assert row['llm_inference_config_id'] == parent.llm_inference_config_id
    assert row['retry_of_execution_id'] == parent.id
    assert row['attempt'] == 2

    payload = service.celery.send_task.call_args.kwargs['kwargs']['payload']
    assert service.celery.send_task.call_args.args[0] == svc_module._AGENT_TASK_NAME
    # Inputs still point at the parent's blobs; output goes under the new run.
    assert payload['inputs'] == STORED_INPUTS
    assert payload['output_prefix'] == (
        f'executions/agents/{parent.entity_id}/{row["id"]}/'
    )
    assert payload['version'] == 5
    assert payload['access_token'] == 'tok'
    assert payload['llm_inference_config_id'] == str(parent.llm_inference_config_id)
    assert payload['variables']['_wf_execution_id'] == str(row['id'])
    service.cloud_storage.save_small_file.assert_not_called()

    assert result.execution_id == row['id']
    assert result.retry_of_execution_id == parent.id
    assert result.attempt == 2


async def test_workflow_retry_sends_name_and_namespace(has_capacity):
    parent = _parent(entity_type='workflow', llm_inference_config_id=None)
    service, _ = _service(parent)

    await service.retry_execution(
        parent,
        access_token=None,
        app_key='key',
        version=3,
        workflow_name='wf',
        namespace='default',
    )

    args = service.celery.send_task.call_args
    payload = args.kwargs['kwargs']['payload']
    assert args.args[0] == svc_module._WORKFLOW_TASK_NAME
    assert payload['workflow_name'] == 'wf'
    assert payload['namespace'] == 'default'
    assert payload['output_prefix'].startswith(
        f'executions/workflows/{parent.entity_id}/'
    )
    assert 'llm_inference_config_id' not in payload


async def test_a_retry_of_a_retry_links_to_its_immediate_parent(has_capacity):
    parent = _parent(attempt=2, retry_of_execution_id=uuid.uuid4())
    service, repo = _service(parent)

    await service.retry_execution(parent, access_token=None, app_key=None, version=1)

    row = repo.create.call_args.kwargs
    assert row['retry_of_execution_id'] == parent.id
    assert row['attempt'] == 3


async def test_legacy_row_is_retried_with_fallbacks(has_capacity):
    parent = _parent(
        version=None,
        output_json_enabled=None,
        llm_inference_config_id=None,
        input_files=None,
    )
    service, repo = _service(parent)

    await service.retry_execution(parent, access_token=None, app_key=None, version=4)

    row = repo.create.call_args.kwargs
    assert row['output_json_enabled'] is True
    assert row['llm_inference_config_id'] is None
    assert row['input_files'] is None
    assert row['version'] == 4


async def test_an_explicit_json_opt_out_is_kept(has_capacity):
    parent = _parent(output_json_enabled=False)
    service, repo = _service(parent)

    await service.retry_execution(parent, access_token=None, app_key=None, version=1)

    assert repo.create.call_args.kwargs['output_json_enabled'] is False


async def test_concurrent_retry_loses_without_enqueueing(has_capacity):
    parent = _parent()
    service, repo = _service(parent)
    repo.create.side_effect = IntegrityError('insert', {}, Exception('duplicate'))

    with pytest.raises(ExecutionNotRetryable):
        await service.retry_execution(
            parent, access_token=None, app_key=None, version=1
        )

    service.celery.send_task.assert_not_called()


async def test_saturated_queue_refuses_before_inserting():
    parent = _parent()
    service, repo = _service(parent)

    with patch.object(
        svc_module,
        'ensure_queue_capacity',
        AsyncMock(side_effect=QueueBackpressure(10000, 10000)),
    ):
        with pytest.raises(QueueBackpressure):
            await service.retry_execution(
                parent, access_token=None, app_key=None, version=1
            )

    repo.create.assert_not_awaited()


@pytest.mark.parametrize('entity', ['agent', 'workflow'])
async def test_new_executions_record_their_run_parameters(has_capacity, entity):
    service, repo = _service(None)
    config_id = uuid.uuid4()

    if entity == 'agent':
        await service.create_and_enqueue_agent(
            agent_id=uuid.uuid4(),
            inputs='hi',
            variables=None,
            output_json_enabled=True,
            access_token=None,
            app_key=None,
            llm_inference_config_id=config_id,
            version=7,
        )
    else:
        await service.create_and_enqueue_workflow(
            workflow_id=uuid.uuid4(),
            workflow_name='wf',
            namespace='default',
            inputs='hi',
            variables=None,
            output_json_enabled=True,
            access_token=None,
            app_key=None,
            version=7,
        )

    row = repo.create.call_args.kwargs
    assert row['version'] == 7
    assert row['output_json_enabled'] is True
    assert row['llm_inference_config_id'] == (config_id if entity == 'agent' else None)
    assert row['retry_of_execution_id'] is None
    assert row['attempt'] == 1


# --- POST /v1/agentic-executions/{execution_id}/retry ---------------------------


def _request():
    req = MagicMock()
    req.headers = {}
    return req


def _route_deps(parent, *, entity_missing=False, config_found=True):
    service = MagicMock()
    service.queue_is_saturated = AsyncMock(return_value=False)
    service.get_retryable_execution = AsyncMock(return_value=parent)
    service.retry_execution = AsyncMock(
        return_value=svc_module.AsyncInferenceResponse(
            execution_id=uuid.uuid4(),
            entity_type=parent.entity_type if parent else 'agent',
            entity_id=parent.entity_id if parent else uuid.uuid4(),
            status_url='/v1/agentic-executions/x',
            retry_of_execution_id=parent.id if parent else None,
            attempt=2,
        )
    )

    lookup = AsyncMock(
        side_effect=ValueError('not found') if entity_missing else None,
        return_value={'version': 9, 'name': 'wf', 'namespace': 'default'},
    )
    agent_crud = MagicMock(get_agent=lookup)
    workflow_crud = MagicMock(get_workflow=lookup)
    llm_config = MagicMock(
        get_public_config=AsyncMock(return_value={'id': 'x'} if config_found else None)
    )
    return service, agent_crud, workflow_crud, llm_config


async def _call(service, agent_crud, workflow_crud, llm_config, execution_id=None):
    with patch.object(
        controller, 'extract_auth_credentials', return_value=('tok', None)
    ):
        return await controller.retry_execution(
            request=_request(),
            execution_id=execution_id or uuid.uuid4(),
            async_agentic_execution_service=service,
            agent_crud_service=agent_crud,
            workflow_crud_service=workflow_crud,
            llm_inference_config_service=llm_config,
            response_formatter=ResponseFormatter(),
        )


async def test_route_retries_an_agent_on_its_current_version():
    parent = _parent()
    deps = _route_deps(parent)
    service, agent_crud, _, _ = deps

    response = await _call(*deps)

    assert response.status_code == 202
    agent_crud.get_agent.assert_awaited_once_with(parent.entity_id)
    kwargs = service.retry_execution.call_args.kwargs
    assert service.retry_execution.call_args.args[0] is parent
    assert kwargs['version'] == 9
    assert kwargs['access_token'] == 'tok'
    assert kwargs['workflow_name'] is None
    body = json.loads(response.body)['data']['data']
    assert body['retry_of_execution_id'] == str(parent.id)
    assert body['attempt'] == 2


async def test_route_passes_workflow_name_and_namespace():
    parent = _parent(entity_type='workflow', llm_inference_config_id=None)
    deps = _route_deps(parent)
    service, _, workflow_crud, llm_config = deps

    response = await _call(*deps)

    assert response.status_code == 202
    workflow_crud.get_workflow.assert_awaited_once_with(parent.entity_id)
    kwargs = service.retry_execution.call_args.kwargs
    assert kwargs['workflow_name'] == 'wf'
    assert kwargs['namespace'] == 'default'
    llm_config.get_public_config.assert_not_awaited()


@pytest.mark.parametrize(
    'side_effect, expected',
    [
        (ValueError('Execution not found'), 404),
        (ExecutionNotRetryable('completed'), 409),
    ],
)
async def test_route_maps_retryability_errors(side_effect, expected):
    deps = _route_deps(_parent())
    service = deps[0]
    service.get_retryable_execution.side_effect = side_effect

    response = await _call(*deps)

    assert response.status_code == expected
    service.retry_execution.assert_not_awaited()


async def test_route_404s_a_deleted_entity():
    deps = _route_deps(_parent(), entity_missing=True)

    response = await _call(*deps)

    assert response.status_code == 404
    deps[0].retry_execution.assert_not_awaited()


async def test_route_404s_a_deleted_llm_config():
    deps = _route_deps(_parent(), config_found=False)

    response = await _call(*deps)

    assert response.status_code == 404
    deps[0].retry_execution.assert_not_awaited()


async def test_route_409s_a_lost_race():
    deps = _route_deps(_parent())
    deps[0].retry_execution.side_effect = ExecutionNotRetryable('already retried')

    response = await _call(*deps)

    assert response.status_code == 409


async def test_route_429s_a_saturated_queue():
    deps = _route_deps(_parent())
    deps[0].queue_is_saturated.return_value = True
    deps[0].backpressure_retry_after_seconds = 30

    response = await _call(*deps)

    assert response.status_code == 429
    assert response.headers['Retry-After'] == '30'
    deps[0].get_retryable_execution.assert_not_awaited()


async def test_route_429s_when_the_queue_fills_at_enqueue():
    deps = _route_deps(_parent())
    deps[0].retry_execution.side_effect = QueueBackpressure(10000, 10000)

    response = await _call(*deps)

    assert response.status_code == 429


# --- is_retryable / retried_by_execution_id on reads -----------------------------


def _record_dict(**overrides):
    values = {
        'id': str(uuid.uuid4()),
        'entity_type': 'agent',
        'entity_id': str(uuid.uuid4()),
        'status': 'failed',
        'attempt': 1,
        'created_at': '2026-11-20T10:00:00',
    }
    values.update(overrides)
    return values


def _read_service(retried_by=None, max_attempts=3):
    """A service whose retry lookup answers with `retried_by` (parent -> child)."""
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = list((retried_by or {}).items())
    session.execute = AsyncMock(return_value=result)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    repo = MagicMock()
    repo.session = MagicMock(return_value=session_cm)
    service = AsyncAgenticExecutionService(
        async_agentic_execution_repository=repo,
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        executions_bucket='bucket',
        celery_client=MagicMock(),
        celery_settings=CeleryProducerSettings(max_execution_attempts=max_attempts),
    )
    return service, session


async def test_a_failed_execution_not_yet_retried_is_retryable():
    record = _record_dict()
    service, _ = _read_service()
    service.cache.get_str.return_value = json.dumps(record)

    result = await service.get_execution_status(uuid.UUID(record['id']))

    assert result.is_retryable is True
    assert result.retried_by_execution_id is None


async def test_a_retried_execution_points_at_its_retry():
    record = _record_dict()
    child_id = uuid.uuid4()
    service, _ = _read_service(retried_by={uuid.UUID(record['id']): child_id})
    service.cache.get_str.return_value = None
    service.repo.find_one = AsyncMock(
        return_value=MagicMock(to_dict=MagicMock(return_value=record))
    )

    result = await service.get_execution_status(uuid.UUID(record['id']))

    assert result.is_retryable is False
    assert result.retried_by_execution_id == child_id


@pytest.mark.parametrize(
    'overrides',
    [
        {'status': 'completed'},
        {'status': 'cancelled'},
        {'status': 'failed', 'attempt': 3},
    ],
)
async def test_rows_that_cannot_be_retried_skip_the_lookup(overrides):
    record = _record_dict(**overrides)
    service, session = _read_service()
    service.cache.get_str.return_value = json.dumps(record)

    result = await service.get_execution_status(uuid.UUID(record['id']))

    assert result.is_retryable is False
    session.execute.assert_not_awaited()


async def test_a_cached_record_from_before_the_columns_is_read_as_attempt_one():
    record = _record_dict()
    del record['attempt']
    service, _ = _read_service()
    service.cache.get_str.return_value = json.dumps(record)

    result = await service.get_execution_status(uuid.UUID(record['id']))

    assert result.attempt == 1
    assert result.is_retryable is True


async def test_a_listing_page_needs_one_lookup():
    failed = _record_dict()
    retried = _record_dict()
    done = _record_dict(status='completed')
    child_id = uuid.uuid4()
    service, session = _read_service(retried_by={uuid.UUID(retried['id']): child_id})
    responses = [
        service._build_status_response(r, generate_urls=False)
        for r in (failed, retried, done)
    ]

    await service._add_retry_state(responses)

    session.execute.assert_awaited_once()
    assert [r.is_retryable for r in responses] == [True, False, False]
    assert [r.retried_by_execution_id for r in responses] == [None, child_id, None]
