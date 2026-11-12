"""DynamicQueryService lets overload through to the 503 handler."""

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
