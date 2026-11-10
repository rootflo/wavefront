"""The dynamic-query execute route caches only fully successful results."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datasource import PostgresConfig
from datasource.types import DataSourceType

from common_module.response_formatter import ResponseFormatter
from plugins_module.controllers import datasource_controller

PG_CONFIG = PostgresConfig('h', 5432, 'db', 'u', 'p')
OK = {'status': 'success', 'error': None, 'description': '', 'result': [{'id': 1}]}
FAILED = {
    'status': 'error',
    'error': 'canceling statement due to statement timeout',
    'description': '',
    'result': [],
}


@pytest.fixture
def plugin():
    with (
        patch.object(
            datasource_controller, 'check_is_admin', AsyncMock(return_value=True)
        ),
        patch.object(
            datasource_controller,
            'get_datasource_config',
            AsyncMock(return_value=(DataSourceType.POSTGRES, PG_CONFIG)),
        ),
        patch.object(datasource_controller, 'DatasourcePlugin') as plugin_class,
    ):
        yield plugin_class.return_value


async def _execute(cache_manager):
    query_service = MagicMock()
    query_service.get_dynamic_yaml_query = AsyncMock(return_value=([{'id': 'q'}], None))
    return await datasource_controller.execute_dynamic_query(
        request=SimpleNamespace(
            state=SimpleNamespace(
                session=SimpleNamespace(role_id='r', user_id='u', session_id='s')
            )
        ),
        datasource_id='ds',
        query_id='q',
        filter=None,
        offset=0,
        limit=10,
        dynamic_query_params=None,
        response_formatter=ResponseFormatter(),
        dynamic_query_yaml_service=query_service,
        user_service=MagicMock(),
        cache_manager=cache_manager,
        feature_flags=MagicMock(),
        force_fetch=1,
    )


@pytest.mark.asyncio
async def test_successful_result_is_cached(plugin):
    plugin.execute_dynamic_query = AsyncMock(return_value={'a': OK, 'b': OK})
    cache_manager = MagicMock()

    response = await _execute(cache_manager)

    assert response.status_code == 200
    cache_manager.add.assert_called_once()


@pytest.mark.asyncio
async def test_result_with_a_failed_query_is_not_cached(plugin):
    plugin.execute_dynamic_query = AsyncMock(return_value={'a': OK, 'b': FAILED})
    cache_manager = MagicMock()

    response = await _execute(cache_manager)

    assert response.status_code == 200
    cache_manager.add.assert_not_called()
