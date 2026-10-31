"""Upload/download endpoints and the SQL-only guard for file storage datasources."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datasource import PostgresConfig, S3FileStorageConfig
from datasource.types import DataSourceType
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from flo_cloud._types import FolderListing, StorageObject
from flo_cloud.exceptions import CloudStorageFileNotFoundError

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import SecretCipher
from dependency_injector import providers
from plugins_module.controllers import datasource_controller
from plugins_module.plugins_container import PluginsContainer

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
FILES_URL = f'/v1/datasources/{DATASOURCE_ID}/files'
FILES_LIST_URL = f'/v1/datasources/{DATASOURCE_ID}/files/list'
FILES_BROWSE_URL = f'/v1/datasources/{DATASOURCE_ID}/files/browse'
FILES_BATCH_URL = f'/v1/datasources/{DATASOURCE_ID}/files/batch'
FOLDERS_URL = f'/v1/datasources/{DATASOURCE_ID}/files/folders'
S3_CONFIG = S3FileStorageConfig(bucket_name='bkt')
PG_CONFIG = PostgresConfig('h', 5432, 'db', 'u', 'p')
AUDIT_SERVICE = MagicMock()


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
def audit():
    AUDIT_SERVICE.reset_mock()
    return AUDIT_SERVICE.record_from_request


def _audited(audit, operation):
    audit.assert_called_once()
    kwargs = audit.call_args.kwargs
    assert kwargs['datasource_id'] == DATASOURCE_ID
    assert kwargs['datasource_type'] == DataSourceType.AWS_S3
    assert kwargs['operation'] == operation
    [entry] = kwargs['entries']
    assert entry.rows_affected == 1
    return entry


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
        instance.resolve_key.side_effect = lambda path: path
        instance.uri_for.side_effect = lambda key: f's3://bkt/{key}'
        instance.download_file.return_value = b'%PDF-1.4'
        instance.download_file_with_content_type.return_value = (b'%PDF-1.4', None)
        instance.list_files.return_value = (['docs/a.pdf', 'test/vishnu'], False)
        instance.delete_file.side_effect = lambda path: f's3://bkt/{path}'
        instance.create_folder.side_effect = lambda path: f's3://bkt/{path}/'
        instance.list_folder.return_value = FolderListing(
            folders=['docs/2025/'],
            files=[
                StorageObject(
                    'docs/a.pdf',
                    12,
                    'application/pdf',
                    datetime(2025, 10, 1, tzinfo=timezone.utc),
                )
            ],
            next_page_token='tok-2',
        )
        yield instance


class TestDelete:
    def test_deletes_and_audits(self, client, admin, datasource_config, plugin, audit):
        response = client.delete(FILES_URL, params={'path': 'docs/a.pdf'})
        assert response.status_code == 200
        assert response.json()['data'] == {
            'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
            'storage_uri': 's3://bkt/docs/a.pdf',
        }
        plugin.delete_file.assert_called_once_with('docs/a.pdf')
        entry = _audited(audit, 'delete')
        assert entry.snapshot == 'deleted'

    def test_datasource_uri(self, client, admin, datasource_config, plugin):
        response = client.delete(
            FILES_URL, params={'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf'}
        )
        assert response.status_code == 200
        plugin.delete_file.assert_called_once_with('docs/a.pdf')

    def test_not_found(self, client, admin, datasource_config, plugin, audit):
        plugin.delete_file.side_effect = CloudStorageFileNotFoundError('bkt', 'missing')
        response = client.delete(FILES_URL, params={'path': 'missing.txt'})
        assert response.status_code == 404
        audit.assert_not_called()

    def test_rejects_sql_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.delete(FILES_URL, params={'path': 'a.txt'})
        assert response.status_code == 400
        plugin.delete_file.assert_not_called()


class TestListFiles:
    def test_returns_relative_and_datasource_paths(
        self, client, admin, datasource_config, plugin
    ):
        response = client.get(FILES_LIST_URL)
        assert response.status_code == 200
        body = response.json()['data']
        assert body['has_next_page'] is False
        assert body['page_number'] == 1
        assert body['files'] == [
            {
                'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
                'relative_path': 'docs/a.pdf',
                'name': 'a.pdf',
            },
            {
                'path': f'datasource://{DATASOURCE_ID}/test/vishnu',
                'relative_path': 'test/vishnu',
                'name': 'vishnu',
            },
        ]
        plugin.list_files.assert_called_once_with('', 50, 1)

    def test_forwards_prefix_and_pagination(
        self, client, admin, datasource_config, plugin
    ):
        response = client.get(
            FILES_LIST_URL, params={'prefix': 'docs', 'page_size': 10, 'page_number': 2}
        )
        assert response.status_code == 200
        plugin.list_files.assert_called_once_with('docs', 10, 2)

    def test_rejects_sql_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.get(FILES_LIST_URL)
        assert response.status_code == 400
        plugin.list_files.assert_not_called()


class TestUpload:
    def test_returns_datasource_uri(
        self, client, admin, datasource_config, plugin, audit
    ):
        response = client.post(
            FILES_URL,
            files={'file': ('a.pdf', b'%PDF-1.4', 'application/pdf')},
            data={'path': 'docs/'},
        )
        assert response.status_code == 201
        assert response.json()['data'] == {
            'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
            'storage_uri': 's3://bkt/docs/a.pdf',
        }
        plugin.upload_file.assert_called_once_with(
            b'%PDF-1.4', 'docs/a.pdf', 'application/pdf'
        )

    def test_audited(self, client, admin, datasource_config, plugin, audit):
        client.post(
            FILES_URL,
            files={'file': ('a.pdf', b'%PDF-1.4', 'application/pdf')},
            data={'path': 'docs/'},
        )
        entry = _audited(audit, 'upload')
        assert entry.table_name == 'docs/a.pdf'
        assert entry.snapshot == 'submitted'
        assert entry.rows == [
            {
                'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
                'storage_uri': 's3://bkt/docs/a.pdf',
                'size_bytes': 8,
                'content_type': 'application/pdf',
            }
        ]

    def test_long_key_clipped_in_audit(
        self, client, admin, datasource_config, plugin, audit
    ):
        key = 'd/' * 300 + 'a.txt'
        client.post(FILES_URL, files={'file': ('a.txt', b'hi')}, data={'path': key})
        entry = _audited(audit, 'upload')
        assert len(entry.table_name) == 512
        assert entry.meta['key_truncated'] is True
        assert entry.rows[0]['path'].endswith(key)

    def test_failed_upload_not_audited(
        self, client, admin, datasource_config, plugin, audit
    ):
        plugin.upload_file.side_effect = RuntimeError('boom')
        with pytest.raises(RuntimeError):
            client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        audit.assert_not_called()

    def test_defaults_to_file_name(self, client, admin, datasource_config, plugin):
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.json()['data']['path'] == f'datasource://{DATASOURCE_ID}/a.txt'

    def test_explicit_path_used_as_key(self, client, admin, datasource_config, plugin):
        response = client.post(
            FILES_URL, files={'file': ('a.txt', b'hi')}, data={'path': 'x/b.txt'}
        )
        assert (
            response.json()['data']['path'] == f'datasource://{DATASOURCE_ID}/x/b.txt'
        )

    def test_non_admin_forbidden(self, client, admin, datasource_config, plugin, audit):
        admin.return_value = False
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 403
        plugin.upload_file.assert_not_called()
        audit.assert_not_called()

    def test_sql_datasource_rejected(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 400
        plugin.upload_file.assert_not_called()

    def test_missing_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (None, None)
        response = client.post(FILES_URL, files={'file': ('a.txt', b'hi')})
        assert response.status_code == 404

    def test_invalid_path(self, client, admin, datasource_config, plugin, audit):
        response = client.post(
            FILES_URL, files={'file': ('a.txt', b'hi')}, data={'path': '../x'}
        )
        assert response.status_code == 400
        plugin.upload_file.assert_not_called()
        audit.assert_not_called()


class TestDownload:
    def test_streams_bytes(self, client, admin, datasource_config, plugin):
        response = client.get(
            FILES_URL, params={'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf'}
        )
        assert response.status_code == 200
        assert response.content == b'%PDF-1.4'
        assert response.headers['content-type'] == 'application/pdf'
        assert 'a.pdf' in response.headers['content-disposition']
        plugin.download_file_with_content_type.assert_called_once_with('docs/a.pdf')

    def test_plain_key(self, client, admin, datasource_config, plugin):
        response = client.get(FILES_URL, params={'path': 'docs/a.pdf'})
        assert response.status_code == 200
        plugin.download_file_with_content_type.assert_called_once_with('docs/a.pdf')

    def test_extensionless_uses_stored_content_type(
        self, client, admin, datasource_config, plugin
    ):
        jpeg = b'\xff\xd8\xff\xe0' + b'\x00' * 16
        plugin.download_file_with_content_type.return_value = (jpeg, 'image/jpeg')
        response = client.get(
            FILES_URL, params={'path': f'datasource://{DATASOURCE_ID}/test/vishnu'}
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'
        assert response.content == jpeg

    def test_extensionless_sniffs_jpeg_when_no_stored_type(
        self, client, admin, datasource_config, plugin
    ):
        jpeg = b'\xff\xd8\xff\xe0' + b'\x00' * 16
        plugin.download_file_with_content_type.return_value = (jpeg, None)
        response = client.get(FILES_URL, params={'path': 'test/vishnu'})
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'

    def test_datasource_id_case_insensitive(
        self, client, admin, datasource_config, plugin
    ):
        path = f'datasource://{DATASOURCE_ID.upper()}/a.pdf'
        assert client.get(FILES_URL, params={'path': path}).status_code == 200

    def test_audited(self, client, admin, datasource_config, plugin, audit):
        client.get(
            FILES_URL, params={'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf'}
        )
        entry = _audited(audit, 'download')
        assert entry.table_name == 'docs/a.pdf'
        assert entry.snapshot == 'read'
        assert entry.rows == [
            {
                'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
                'storage_uri': 's3://bkt/docs/a.pdf',
                'size_bytes': 8,
                'content_type': 'application/pdf',
            }
        ]

    def test_other_datasource_rejected(
        self, client, admin, datasource_config, plugin, audit
    ):
        path = 'datasource://22222222-2222-2222-2222-222222222222/a.pdf'
        response = client.get(FILES_URL, params={'path': path})
        assert response.status_code == 400
        assert 'belongs to datasource' in response.text
        plugin.download_file_with_content_type.assert_not_called()
        audit.assert_not_called()

    def test_malformed_datasource_uri(self, client, admin, datasource_config, plugin):
        response = client.get(FILES_URL, params={'path': 'datasource://only-id'})
        assert response.status_code == 400
        plugin.download_file_with_content_type.assert_not_called()

    def test_not_found(self, client, admin, datasource_config, plugin, audit):
        plugin.download_file_with_content_type.side_effect = (
            CloudStorageFileNotFoundError('bkt', 'a')
        )
        response = client.get(FILES_URL, params={'path': 'missing.txt'})
        assert response.status_code == 404
        audit.assert_not_called()

    def test_provider_uri_rejected(self, client, admin, datasource_config, plugin):
        plugin.resolve_key.side_effect = ValueError('relative to the base path')
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


class TestBrowse:
    def test_returns_one_level_with_details(
        self, client, admin, datasource_config, plugin
    ):
        response = client.get(
            FILES_BROWSE_URL, params={'prefix': 'docs/', 'page_token': 'tok-1'}
        )
        assert response.status_code == 200
        assert response.json()['data'] == {
            'prefix': 'docs/',
            'folders': [{'name': '2025', 'prefix': 'docs/2025/'}],
            'files': [
                {
                    'path': f'datasource://{DATASOURCE_ID}/docs/a.pdf',
                    'relative_path': 'docs/a.pdf',
                    'name': 'a.pdf',
                    'size': 12,
                    'content_type': 'application/pdf',
                    'updated_at': '2025-10-01T00:00:00+00:00',
                }
            ],
            'next_page_token': 'tok-2',
        }
        plugin.list_folder.assert_called_once_with('docs/', 100, 'tok-1')

    def test_invalid_prefix(self, client, admin, datasource_config, plugin):
        plugin.list_folder.side_effect = ValueError('bad path')
        response = client.get(FILES_BROWSE_URL, params={'prefix': '../x'})
        assert response.status_code == 400

    def test_rejects_sql_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.get(FILES_BROWSE_URL)
        assert response.status_code == 400
        plugin.list_folder.assert_not_called()

    def test_non_admin_forbidden(self, client, admin, datasource_config, plugin):
        admin.return_value = False
        response = client.get(FILES_BROWSE_URL)
        assert response.status_code == 403


class TestCreateFolder:
    def test_creates_and_audits(self, client, admin, datasource_config, plugin, audit):
        response = client.post(FOLDERS_URL, json={'path': '/reports/2025/'})
        assert response.status_code == 201
        assert response.json()['data'] == {
            'path': f'datasource://{DATASOURCE_ID}/reports/2025/',
            'prefix': 'reports/2025/',
            'storage_uri': 's3://bkt/reports/2025/',
        }
        plugin.create_folder.assert_called_once_with('reports/2025')
        entry = _audited(audit, 'upload')
        assert entry.rows[0]['size_bytes'] == 0

    @pytest.mark.parametrize('path', ['', '/', '../up'])
    def test_rejects_bad_path(
        self, client, admin, datasource_config, plugin, audit, path
    ):
        response = client.post(FOLDERS_URL, json={'path': path})
        assert response.status_code == 400
        plugin.create_folder.assert_not_called()
        audit.assert_not_called()

    def test_non_admin_forbidden(self, client, admin, datasource_config, plugin):
        admin.return_value = False
        response = client.post(FOLDERS_URL, json={'path': 'x'})
        assert response.status_code == 403


class TestBatchUpload:
    def test_uploads_each_file_to_its_path(
        self, client, admin, datasource_config, plugin, audit
    ):
        response = client.post(
            FILES_BATCH_URL,
            files=[
                ('files', ('a.txt', b'aa', 'text/plain')),
                ('files', ('b.png', b'bb', 'image/png')),
            ],
            data={'paths': ['photos/a.txt', 'photos/2025/']},
        )
        assert response.status_code == 200
        assert response.json()['data'] == {
            'uploaded': 2,
            'failed': 0,
            'results': [
                {
                    'index': 0,
                    'path': f'datasource://{DATASOURCE_ID}/photos/a.txt',
                    'storage_uri': 's3://bkt/photos/a.txt',
                },
                {
                    'index': 1,
                    'path': f'datasource://{DATASOURCE_ID}/photos/2025/b.png',
                    'storage_uri': 's3://bkt/photos/2025/b.png',
                },
            ],
        }
        audit.assert_called_once()
        assert len(audit.call_args.kwargs['entries']) == 2

    def test_one_failure_does_not_stop_the_rest(
        self, client, admin, datasource_config, plugin, audit
    ):
        def upload(content, path, content_type):
            if path == 'bad.txt':
                raise RuntimeError('storage down')
            return f's3://bkt/{path}'

        plugin.upload_file.side_effect = upload
        response = client.post(
            FILES_BATCH_URL,
            files=[
                ('files', ('bad.txt', b'x', 'text/plain')),
                ('files', ('ok.txt', b'y', 'text/plain')),
            ],
            data={'paths': ['bad.txt', 'ok.txt']},
        )
        body = response.json()['data']
        assert response.status_code == 200
        assert (body['uploaded'], body['failed']) == (1, 1)
        assert body['results'][0] == {'index': 0, 'error': 'Upload failed'}
        assert body['results'][1]['path'].endswith('/ok.txt')
        assert len(audit.call_args.kwargs['entries']) == 1

    def test_paths_must_match_files(self, client, admin, datasource_config, plugin):
        response = client.post(
            FILES_BATCH_URL,
            files=[('files', ('a.txt', b'a', 'text/plain'))],
            data={'paths': ['a.txt', 'b.txt']},
        )
        assert response.status_code == 400
        plugin.upload_file.assert_not_called()

    def test_too_many_files(self, client, admin, datasource_config, plugin):
        count = datasource_controller.MAX_BATCH_UPLOAD_FILES + 1
        response = client.post(
            FILES_BATCH_URL,
            files=[('files', (f'{i}.txt', b'x', 'text/plain')) for i in range(count)],
            data={'paths': [f'{i}.txt' for i in range(count)]},
        )
        assert response.status_code == 400
        plugin.upload_file.assert_not_called()

    def test_rejects_sql_datasource(self, client, admin, datasource_config, plugin):
        datasource_config.return_value = (DataSourceType.POSTGRES, PG_CONFIG)
        response = client.post(
            FILES_BATCH_URL,
            files=[('files', ('a.txt', b'a', 'text/plain'))],
            data={'paths': ['a.txt']},
        )
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
            find_one_and_update=AsyncMock(
                return_value=SimpleNamespace(id='x', type='aws_s3')
            ),
        )
        with patch.object(
            datasource_controller.Datasource, 'to_dict', return_value={'config': {}}
        ):
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
                secret_cipher=SecretCipher(enabled=False),
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


@pytest.mark.parametrize(
    'filename, content, stored, expected',
    [
        ('vishnu', b'\xff\xd8\xff\xe0xx', 'image/jpeg', 'image/jpeg'),
        ('vishnu', b'\xff\xd8\xff\xe0xx', None, 'image/jpeg'),
        ('vishnu', b'\x89PNG\r\n\x1a\nxx', None, 'image/png'),
        ('photo.jpg', b'not-an-image', None, 'image/jpeg'),
        ('blob', b'plain', 'application/octet-stream', 'application/octet-stream'),
        ('blob', b'plain', None, 'application/octet-stream'),
        ('photo.jpg', b'not-an-image', 'binary/octet-stream', 'image/jpeg'),
        ('vishnu', b'\xff\xd8\xff\xe0xx', 'binary/octet-stream', 'image/jpeg'),
    ],
)
def test_resolve_download_media_type(filename, content, stored, expected):
    assert (
        datasource_controller._resolve_download_media_type(filename, content, stored)
        == expected
    )


def test_upload_stores_html_as_octet_stream(client, admin, datasource_config, plugin):
    response = client.post(
        FILES_URL, files={'file': ('x.html', b'<script></script>', 'text/html')}
    )
    assert response.status_code == 201
    plugin.upload_file.assert_called_once_with(
        b'<script></script>', 'x.html', 'application/octet-stream'
    )
