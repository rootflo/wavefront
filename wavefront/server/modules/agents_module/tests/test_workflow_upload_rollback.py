"""Workflow create/update roll back their new rows when the YAML upload fails,
so a busy storage pool (503) or a storage error leaves nothing half-written."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agents_module.services import workflow_crud_service as module
from agents_module.services.workflow_crud_service import WorkflowCrudService
from common_module.blocking_io import BlockingPoolBusyError
from flo_testing import add_async_cache_methods


def make_service():
    service = object.__new__(WorkflowCrudService)
    service._validate_yaml_content = AsyncMock()
    service.namespace_service = Mock(
        get_or_create_namespace=AsyncMock(return_value={'name': 'ns'})
    )
    workflow = SimpleNamespace(id='wf-1', namespace='ns', name='flow')
    service.workflow_repository = Mock(
        find_one=AsyncMock(return_value=None),
        create=AsyncMock(return_value=workflow),
        delete_all=AsyncMock(),
    )
    service.workflow_version_repository = Mock(
        create=AsyncMock(), delete_all=AsyncMock()
    )
    service.cloud_storage_manager = Mock()
    service.cache_manager = add_async_cache_methods(Mock())
    service.bucket_name = 'bucket'
    return service, workflow


@pytest.fixture
def busy_pool(monkeypatch):
    async def busy(*_args, **_kwargs):
        raise BlockingPoolBusyError('storage', 10.0)

    monkeypatch.setattr(module, 'run_in_pool', busy)


@pytest.mark.usefixtures('busy_pool')
async def test_create_rolls_back_when_the_upload_is_refused():
    service, workflow = make_service()

    with pytest.raises(BlockingPoolBusyError):
        await service.create_workflow('flow', 'ns', 'arium: {}\n')

    service.workflow_repository.delete_all.assert_awaited_once_with(id=workflow.id)


@pytest.mark.usefixtures('busy_pool')
async def test_new_version_is_rolled_back_when_the_upload_is_refused():
    service, workflow = make_service()
    service.workflow_repository.find_one = AsyncMock(return_value=workflow)
    service.workflow_version_repository.find = AsyncMock(
        return_value=[SimpleNamespace(version=1, is_deleted=False)]
    )

    with pytest.raises(BlockingPoolBusyError):
        await service.update_workflow(
            workflow_id=workflow.id,
            yaml_content='arium: {}\n',
            version=1,
            create_new_version=True,
        )

    service.workflow_version_repository.delete_all.assert_awaited_once_with(
        workflow_id=workflow.id, version=2
    )


async def test_new_workflow_version_is_rolled_back_when_redis_is_down():
    """The strict pre-invalidation fails (503) after the version row exists:
    the row must still be removed, not left without YAML."""
    from db_repo_module.cache.cache_manager import CacheUnavailableError

    service, workflow = make_service()
    service.workflow_repository.find_one = AsyncMock(return_value=workflow)
    service.workflow_version_repository.find = AsyncMock(
        return_value=[SimpleNamespace(version=1, is_deleted=False)]
    )
    service.cache_manager.remove.side_effect = CacheUnavailableError('redis down')

    with pytest.raises(CacheUnavailableError):
        await service.update_workflow(
            workflow_id=workflow.id,
            yaml_content='arium: {}\n',
            version=1,
            create_new_version=True,
        )

    service.workflow_version_repository.delete_all.assert_awaited_once_with(
        workflow_id=workflow.id, version=2
    )
    service.cloud_storage_manager.save_small_file.assert_not_called()


async def test_new_agent_version_is_rolled_back_when_redis_is_down():
    from agents_module.services.agent_crud_service import AgentCrudService
    from db_repo_module.cache.cache_manager import CacheUnavailableError

    service = object.__new__(AgentCrudService)
    agent = SimpleNamespace(id='ag-1', namespace='ns', name='bot', current_version=1)
    service.agent_repository = Mock(find_one=AsyncMock(return_value=agent))
    service.agent_version_repository = Mock(
        find=AsyncMock(return_value=[SimpleNamespace(version=1, is_deleted=False)]),
        create=AsyncMock(),
        delete_all=AsyncMock(),
    )
    service._validate_yaml_content = AsyncMock()
    service.cloud_storage_manager = Mock()
    service.bucket_name = 'bucket'
    service.cache_manager = add_async_cache_methods(Mock())
    service.cache_manager.remove.side_effect = CacheUnavailableError('redis down')

    with pytest.raises(CacheUnavailableError):
        await service.update_agent(
            agent_id=agent.id,
            yaml_content='agent: {}\n',
            tool_available=[],
            version=1,
            create_new_version=True,
        )

    service.agent_version_repository.delete_all.assert_awaited_once_with(
        agent_id=agent.id, version=2
    )
    service.cloud_storage_manager.save_small_file.assert_not_called()
