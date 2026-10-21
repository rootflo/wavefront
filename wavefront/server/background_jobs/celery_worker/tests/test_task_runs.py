"""Agent / workflow task run paths with services mocked."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from celery_worker.tasks import agent_task, workflow_task


def _services_mock():
    services = MagicMock()
    services.cache.namespace = 'floware'
    services.cache.xadd.return_value = '1-0'
    services.cloud_storage = MagicMock()
    services.agent_inference.perform_inference_v2 = AsyncMock(
        return_value=('agent-out', 0.5, 'ns')
    )
    services.workflow_inference.perform_inference_v2 = AsyncMock(
        return_value=('wf-out', 1.2, [])
    )
    return services


@pytest.mark.asyncio
async def test_agent_run_publishes_in_progress_then_completed():
    services = _services_mock()
    payload = {
        'execution_id': str(uuid4()),
        'entity_type': 'agent',
        'entity_id': str(uuid4()),
        'inputs': 'hello',
        'variables': {},
        'output_prefix': 'exec/',
        'execution_bucket': 'app-bucket',
        'output_json_enabled': True,
    }

    with (
        patch.object(agent_task, 'get_services', return_value=services),
        patch.object(agent_task, 'reconstruct_inputs', return_value='hello'),
        patch.object(agent_task, 'save_json') as save_json,
    ):
        await agent_task._run(MagicMock(), payload)

    statuses = [c.args[1]['status'] for c in services.cache.xadd.call_args_list]
    assert statuses == ['in_progress', 'completed']
    assert save_json.call_count == 2


@pytest.mark.asyncio
async def test_agent_run_publishes_failed_and_reraises():
    services = _services_mock()
    services.agent_inference.perform_inference_v2 = AsyncMock(
        side_effect=RuntimeError('boom')
    )
    payload = {
        'execution_id': str(uuid4()),
        'entity_type': 'agent',
        'entity_id': str(uuid4()),
        'inputs': 'hello',
        'variables': {},
        'output_prefix': 'exec/',
        'execution_bucket': 'app-bucket',
    }

    with (
        patch.object(agent_task, 'get_services', return_value=services),
        patch.object(agent_task, 'reconstruct_inputs', return_value='hello'),
    ):
        with pytest.raises(RuntimeError, match='boom'):
            await agent_task._run(MagicMock(), payload)

    statuses = [c.args[1]['status'] for c in services.cache.xadd.call_args_list]
    assert statuses == ['in_progress', 'failed']
    assert services.cache.xadd.call_args_list[-1].args[1]['error'] == 'boom'


@pytest.mark.asyncio
async def test_workflow_run_publishes_completed():
    services = _services_mock()
    payload = {
        'execution_id': str(uuid4()),
        'entity_type': 'workflow',
        'entity_id': str(uuid4()),
        'workflow_name': 'wf',
        'namespace': 'default',
        'inputs': 'hello',
        'variables': {},
        'output_prefix': 'exec/',
        'execution_bucket': 'app-bucket',
    }

    with (
        patch.object(workflow_task, 'get_services', return_value=services),
        patch.object(workflow_task, 'reconstruct_inputs', return_value='hello'),
        patch.object(workflow_task, 'save_json'),
    ):
        await workflow_task._run(MagicMock(), payload)

    statuses = [c.args[1]['status'] for c in services.cache.xadd.call_args_list]
    assert statuses == ['in_progress', 'completed']


@pytest.mark.asyncio
async def test_workflow_run_publishes_failed_and_reraises():
    services = _services_mock()
    services.workflow_inference.perform_inference_v2 = AsyncMock(
        side_effect=RuntimeError('wf boom')
    )
    payload = {
        'execution_id': str(uuid4()),
        'entity_type': 'workflow',
        'entity_id': str(uuid4()),
        'workflow_name': 'wf',
        'namespace': 'default',
        'inputs': 'hello',
        'variables': {},
        'output_prefix': 'exec/',
        'execution_bucket': 'app-bucket',
    }

    with (
        patch.object(workflow_task, 'get_services', return_value=services),
        patch.object(workflow_task, 'reconstruct_inputs', return_value='hello'),
    ):
        with pytest.raises(RuntimeError, match='wf boom'):
            await workflow_task._run(MagicMock(), payload)

    statuses = [c.args[1]['status'] for c in services.cache.xadd.call_args_list]
    assert statuses == ['in_progress', 'failed']


@pytest.mark.asyncio
async def test_agent_run_list_result_uses_last_message_content():
    services = _services_mock()
    turn = MagicMock()
    turn.content = 'final-answer'
    services.agent_inference.perform_inference_v2 = AsyncMock(
        return_value=([turn], 0.1, 'ns')
    )
    payload = {
        'execution_id': str(uuid4()),
        'entity_type': 'agent',
        'entity_id': str(uuid4()),
        'inputs': 'hello',
        'variables': {},
        'output_prefix': 'exec/',
        'execution_bucket': 'app-bucket',
    }

    with (
        patch.object(agent_task, 'get_services', return_value=services),
        patch.object(agent_task, 'reconstruct_inputs', return_value='hello'),
        patch.object(
            agent_task, 'serialize_conversation_trace', return_value=[{'n': 1}]
        ),
        patch.object(agent_task, 'save_json') as save_json,
        patch.object(agent_task, 'build_history', return_value={'ok': True}) as history,
    ):
        await agent_task._run(MagicMock(), payload)

    history.assert_called_once()
    assert history.call_args.args[1] == 'final-answer'
    assert history.call_args.args[3] == [{'n': 1}]
    assert save_json.call_count == 2


def test_execute_agent_task_uses_shared_event_loop():
    payload = {'execution_id': 'x'}
    loop = MagicMock()
    with (
        patch.object(agent_task, 'get_event_loop', return_value=loop) as get_loop,
        patch.object(agent_task, '_run', new_callable=AsyncMock),
    ):
        agent_task.execute_agent_task.run(payload)
        get_loop.assert_called_once()
        loop.run_until_complete.assert_called_once()
        assert loop.run_until_complete.call_args.args[0] is not None


def test_execute_workflow_task_uses_shared_event_loop():
    payload = {'execution_id': 'x'}
    loop = MagicMock()
    with (
        patch.object(workflow_task, 'get_event_loop', return_value=loop),
        patch.object(workflow_task, '_run', new_callable=AsyncMock),
    ):
        workflow_task.execute_workflow_task.run(payload)
        loop.run_until_complete.assert_called_once()
