"""Admin-only guard on the row update and delete endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datasource import PostgresConfig
from datasource.types import DataSourceType
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from flo_cloud.postgres import RowMutationResult

from common_module.common_container import CommonContainer
from dependency_injector import providers
from plugins_module.controllers import datasource_controller
from plugins_module.plugins_container import PluginsContainer

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
RESOURCES_URL = f'/v1/datasources/{DATASOURCE_ID}/resources'
PG_CONFIG = PostgresConfig('h', 5432, 'db', 'u', 'p')
AUDIT_SERVICE = MagicMock(capture_limit=100)

UPDATE = ('PATCH', f'{RESOURCES_URL}/orders', {'filter': "id eq '1'", 'data': {'a': 1}})
UPDATE_MULTI = (
    'PATCH',
    f'{RESOURCES_URL}/update',
    {'updates': [{'table_name': 'orders', 'filter': "id eq '1'", 'data': {'a': 1}}]},
)
DELETE = ('DELETE', f'{RESOURCES_URL}/orders', {'filter': "id eq '1'"})


@pytest.fixture(scope='module')
def client():
    container = CommonContainer()
    container.wire(modules=[datasource_controller])
    plugins = PluginsContainer()
    plugins.datasource_audit_service.override(providers.Object(AUDIT_SERVICE))
    plugins.wire(modules=[datasource_controller])
    app = FastAPI()

    @app.middleware('http')
    async def session(request: Request, call_next):
        request.state.session = SimpleNamespace(role_id='role', user_id='user')
        return await call_next(request)

    app.include_router(datasource_controller.datasource_router)
    yield TestClient(app)
    plugins.unwire()
    container.unwire()


@pytest.fixture
def admin():
    with patch.object(
        datasource_controller, 'check_is_admin', AsyncMock(return_value=True)
    ) as mock:
        yield mock


@pytest.fixture
def datasource_config():
    with patch.object(
        datasource_controller,
        'get_datasource_config',
        AsyncMock(return_value=(DataSourceType.POSTGRES, PG_CONFIG)),
    ) as mock:
        yield mock


@pytest.fixture
def plugin():
    with patch.object(datasource_controller, 'DatasourcePlugin') as plugin_class:
        instance = plugin_class.return_value
        result = RowMutationResult(table_name='orders', rows_affected=1)
        instance.update_rows_json.return_value = result
        instance.update_rows_json_multi.return_value = [result]
        instance.delete_rows_json.return_value = result
        yield instance


@pytest.mark.parametrize(
    'method, url, body, plugin_method',
    [
        (*UPDATE, 'update_rows_json'),
        (*UPDATE_MULTI, 'update_rows_json_multi'),
        (*DELETE, 'delete_rows_json'),
    ],
    ids=['update', 'update_multi', 'delete'],
)
class TestAdminOnly:
    def test_non_admin_forbidden(
        self, client, admin, datasource_config, plugin, method, url, body, plugin_method
    ):
        admin.return_value = False
        AUDIT_SERVICE.reset_mock()

        response = client.request(method, url, json=body)

        assert response.status_code == 403
        getattr(plugin, plugin_method).assert_not_called()
        datasource_config.assert_not_called()
        AUDIT_SERVICE.record_from_request.assert_not_called()

    def test_admin_allowed(
        self, client, admin, datasource_config, plugin, method, url, body, plugin_method
    ):
        response = client.request(method, url, json=body)

        assert response.status_code == 200
        getattr(plugin, plugin_method).assert_called_once()
