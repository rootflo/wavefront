"""Upload/download endpoints and the SQL-only guard for file storage datasources."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from datasource import PostgresConfig, S3FileStorageConfig
from datasource.types import DataSourceType
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from flo_cloud.exceptions import CloudStorageFileNotFoundError

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from plugins_module.controllers import datasource_controller

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
FILES_URL = f'/v1/datasources/{DATASOURCE_ID}/files'
S3_CONFIG = S3FileStorageConfig(bucket_name='bkt')
PG_CONFIG = PostgresConfig('h', 5432, 'db', 'u', 'p')


@pytest.fixture(scope='module')
def client():
    container = CommonContainer()
    container.wire(modules=[datasource_controller])
    app = FastAPI()

    @app.middleware('http')
    async def session(request: Request, call_next):
        request.state.session = SimpleNamespace(role_id='role', user_id='user')
        return await call_next(request)

    app.include_router(datasource_controller.datasource_router)
    yield TestClient(app)
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
        AsyncMock(return_value=(DataSourceType.AWS_S3, S3_CONFIG)),
    ) as mock:
        yield mock


@pytest.fixture
def plugin():
    with patch.object(datasource_controller, 'FileStoragePlugin') as plugin_class:
        instance = plugin_class.return_value
        instance.upload_file.side_effect = (
            lambda content, path, content_type: f's3://bkt/{path}'
        )
        instance.resolve_key.side_effect = lambda path: path.removeprefix('s3://bkt/')
        instance.download_file.return_value = b'%PDF-1.4'
        yield instance


class TestUpload:
    def test_returns_full_uri(self, client, admin, datasource_config, plugin):
        response = client.post(
            FILES_URL,
            files={'file': ('a.pdf', b'%PDF-1.4', 'application/pdf')},
            data={'path': 'docs/'},
        )
        assert response.status_code == 201
        assert response.json()['data'] == {'path': 's3://bkt/docs/a.pdf'}
        plugin.upload_file.assert_called_once_with(
            b'%PDF-1.4', 'docs/a.pdf', 'application/pdf'
        )

    def test_defaults_to_file_name(self, client, admin, datasource_config, plugin):
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.json()['data'] == {'path': 's3://bkt/a.txt'}

    def test_explicit_path_used_as_key(self, client, admin, datasource_config, plugin):
        response = client.post(
            FILES_URL, files={'file': ('a.txt', b'hi')}, data={'path': 'x/b.txt'}
        )
        assert response.json()['data'] == {'path': 's3://bkt/x/b.txt'}

    def test_non_admin_forbidden(self, client, admin, datasource_config, plugin):
        admin.return_value = False
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 403
        plugin.upload_file.assert_not_called()

    def test_sql_datasource_rejected(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 400
        plugin.upload_file.assert_not_called()

    def test_missing_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (None, None)
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 404

    def test_invalid_path(self, client, admin, datasource_config, plugin):
        plugin.upload_file.side_effect = ValueError('bad path')
        response = client.post(
            FILES_URL, files={'file': ('a.txt', b'hi')}, data={'path': '../x'}
        )
        assert response.status_code == 400


class TestDownload:
    def test_streams_bytes(self, client, admin, datasource_config, plugin):
        response = client.get(FILES_URL, params={'path': 's3://bkt/docs/a.pdf'})
        assert response.status_code == 200
        assert response.content == b'%PDF-1.4'
        assert response.headers['content-type'] == 'application/pdf'
        assert 'a.pdf' in response.headers['content-disposition']
        plugin.download_file.assert_called_once_with('s3://bkt/docs/a.pdf')

    def test_not_found(self, client, admin, datasource_config, plugin):
        plugin.download_file.side_effect = CloudStorageFileNotFoundError('bkt', 'a')
        response = client.get(FILES_URL, params={'path': 'missing.txt'})
        assert response.status_code == 404

    def test_path_outside_bucket(self, client, admin, datasource_config, plugin):
        plugin.resolve_key.side_effect = ValueError('does not match')
        response = client.get(FILES_URL, params={'path': 's3://other/a'})
        assert response.status_code == 400

    def test_path_required(self, client, admin, datasource_config, plugin):
        assert client.get(FILES_URL).status_code == 422

    def test_non_admin_forbidden(self, client, admin, datasource_config, plugin):
        admin.return_value = False
        response = client.get(FILES_URL, params={'path': 'a.txt'})
        assert response.status_code == 403

    def test_sql_datasource_rejected(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.get(FILES_URL, params={'path': 'a.txt'})
        assert response.status_code == 400


def test_sql_endpoint_rejects_file_storage(client, admin, datasource_config):
    with patch.object(datasource_controller, 'DatasourcePlugin') as sql_plugin:
        response = client.get(f'/v1/datasources/{DATASOURCE_ID}/resources')
    assert response.status_code == 400
    sql_plugin.assert_not_called()


def test_test_connection_uses_file_storage_plugin(
    client, admin, datasource_config, plugin
):
    plugin.test_connection = AsyncMock(return_value=True)
    with patch.object(datasource_controller, 'DatasourcePlugin') as sql_plugin:
        response = client.post(f'/v1/datasources/{DATASOURCE_ID}/test-connection')
    assert response.status_code == 200
    assert response.json() is True
    sql_plugin.assert_not_called()


@pytest.mark.parametrize(
    'path, filename, expected',
    [
        (None, 'a.txt', 'a.txt'),
        ('', 'dir\\a.txt', 'a.txt'),
        ('docs/', 'a.txt', 'docs/a.txt'),
        ('docs/b.txt', 'a.txt', 'docs/b.txt'),
    ],
)
def test_upload_target_path(path, filename, expected):
    assert datasource_controller._upload_target_path(path, filename) == expected


def test_upload_target_path_needs_name():
    with pytest.raises(ValueError):
        datasource_controller._upload_target_path(None, None)


class TestUpdateFileStorageDatasource:
    S3_STORED = {'bucket_name': 'bkt', 'region_name': 'us-east-1'}

    @pytest.fixture
    def repository(self):
        existing = SimpleNamespace(type='aws_s3', config=dict(self.S3_STORED))
        repository = SimpleNamespace(
            find_one=AsyncMock(return_value=existing),
            find_one_and_update=AsyncMock(return_value=SimpleNamespace(id='x')),
        )
        with patch.object(datasource_controller.Datasource, 'to_dict', return_value={}):
            yield repository

    async def _patch(self, repository, existing_type=None, **payload):
        if existing_type:
            repository.find_one.return_value.type = existing_type
        request = SimpleNamespace(
            state=SimpleNamespace(session=SimpleNamespace(role_id='role'))
        )
        with patch.object(datasource_controller, 'invalidate_datasources_cache'):
            return await datasource_controller.update_datasource(
                request,
                DATASOURCE_ID,
                datasource_controller.UpdateDatasourcePayload(**payload),
                response_formatter=ResponseFormatter(),
                datasource_repository=repository,
                cache_manager=None,
            )

    async def test_rename_allowed(self, admin, repository):
        response = await self._patch(repository, name='renamed')
        assert response.status_code == 200
        repository.find_one_and_update.assert_awaited_once_with(
            filters={'id': DATASOURCE_ID}, refresh=True, name='renamed'
        )

    async def test_unchanged_type_and_config_ignored(self, admin, repository):
        response = await self._patch(
            repository,
            name='renamed',
            type='aws_s3',
            config=json.dumps(self.S3_STORED),
        )
        assert response.status_code == 200
        repository.find_one_and_update.assert_awaited_once_with(
            filters={'id': DATASOURCE_ID}, refresh=True, name='renamed'
        )

    @pytest.mark.parametrize(
        'payload',
        [
            {'type': 'gcs'},
            {'type': 'azure_blob_storage'},
            {'type': 'postgres'},
            {'config': json.dumps({'bucket_name': 'other'})},
        ],
    )
    async def test_type_or_config_change_rejected(self, admin, repository, payload):
        response = await self._patch(repository, **payload)
        assert response.status_code == 400
        repository.find_one_and_update.assert_not_awaited()

    async def test_sql_cannot_become_file_storage(self, admin, repository):
        response = await self._patch(
            repository, existing_type='postgres', type='aws_s3'
        )
        assert response.status_code == 400
        repository.find_one_and_update.assert_not_awaited()


@pytest.mark.parametrize(
    'content_type, expected',
    [
        ('application/pdf', 'application/pdf'),
        ('text/csv; charset=utf-8', 'text/csv; charset=utf-8'),
        ('text/html', 'application/octet-stream'),
        ('Image/SVG+XML', 'application/octet-stream'),
        ('application/xhtml+xml; charset=utf-8', 'application/octet-stream'),
        (None, None),
        ('', None),
    ],
)
def test_stored_content_type(content_type, expected):
    assert datasource_controller._stored_content_type(content_type) == expected


def test_upload_stores_html_as_octet_stream(client, admin, datasource_config, plugin):
    response = client.post(
        FILES_URL, files={'file': ('x.html', b'<script></script>', 'text/html')}
    )
    assert response.status_code == 201
    plugin.upload_file.assert_called_once_with(
        b'<script></script>', 'x.html', 'application/octet-stream'
    )
