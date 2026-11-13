"""DynamicQueryService: overload reaches the 503 handler, and a cancelled
request does not split a YAML file from its metadata."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datasource.executor import DatasourceBusyError

from plugins_module.services import dynamic_query_service
from plugins_module.services.dynamic_query_service import DynamicQueryService


def _service():
    return DynamicQueryService(
        cloud_storage_manager=MagicMock(),
        dynamic_query_repo=MagicMock(upsert=AsyncMock()),
        bucket_name='bucket',
    )


@pytest.mark.asyncio
async def test_yaml_upload_reports_busy_as_busy_not_as_a_bad_upload():
    with patch.object(
        dynamic_query_service,
        'run_blocking',
        AsyncMock(side_effect=DatasourceBusyError('busy')),
    ):
        with pytest.raises(DatasourceBusyError):
            await _service().store_yaml_to_bucket({'id': 'q'}, 'ds')


@pytest.mark.asyncio
async def test_yaml_upload_still_wraps_other_storage_failures():
    with patch.object(
        dynamic_query_service,
        'run_blocking',
        AsyncMock(side_effect=OSError('bucket unreachable')),
    ):
        with pytest.raises(ValueError, match='Failed to upload YAML file'):
            await _service().store_yaml_to_bucket({'id': 'q'}, 'ds')


def _slow_storage():
    """A storage call that stays in progress until the test releases it."""
    release = asyncio.Event()
    started = asyncio.Event()

    async def run_blocking(*args, **kwargs):
        started.set()
        await release.wait()

    return run_blocking, started, release


@pytest.mark.asyncio
async def test_cancelled_upload_still_records_the_saved_file():
    run_blocking, started, release = _slow_storage()
    service = _service()
    with patch.object(dynamic_query_service, 'run_blocking', run_blocking):
        upload = asyncio.ensure_future(service.store_yaml_to_bucket({'id': 'q'}, 'ds'))
        await started.wait()
        upload.cancel()  # the client went away mid-upload
        with pytest.raises(asyncio.CancelledError):
            await upload
        release.set()  # the storage write completes anyway
        for _ in range(100):
            if service.dynamic_query_repo.upsert.await_count:
                break
            await asyncio.sleep(0.01)

    service.dynamic_query_repo.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_delete_still_removes_the_record():
    run_blocking, started, release = _slow_storage()
    service = _service()
    service.dynamic_query_repo.find_one = AsyncMock(
        return_value=MagicMock(file_path='dynamic_query/v1/q.yaml')
    )
    service.dynamic_query_repo.delete_all = AsyncMock()
    with patch.object(dynamic_query_service, 'run_blocking', run_blocking):
        delete = asyncio.ensure_future(service.delete_dynamic_query('ds', 'q'))
        await started.wait()
        delete.cancel()
        with pytest.raises(asyncio.CancelledError):
            await delete
        release.set()
        for _ in range(100):
            if service.dynamic_query_repo.delete_all.await_count:
                break
            await asyncio.sleep(0.01)

    service.dynamic_query_repo.delete_all.assert_awaited_once_with(name='q')
