"""FileStoragePlugin: config validation, key/URI handling and provider wiring."""

from unittest.mock import MagicMock, patch

import pytest
from datasource import (
    AzureBlobStorageConfig,
    DatasourcePlugin,
    DataSourceType,
    FileStoragePlugin,
    GCSFileStorageConfig,
    PostgresConfig,
    S3FileStorageConfig,
    build_file_storage_config,
    is_file_storage_type,
)
from flo_cloud.exceptions import CloudStorageFileNotFoundError

CLOUD_STORAGE = 'flo_cloud.cloud_storage'
AZURE_URL = 'https://acct.blob.core.windows.net'


@pytest.fixture
def s3_handler():
    with patch(f'{CLOUD_STORAGE}.S3Storage') as storage_class:
        handler = storage_class.return_value
        handler.get_bucket_key.side_effect = _parse_uri
        yield storage_class, handler


@pytest.fixture
def gcs_handler():
    with patch(f'{CLOUD_STORAGE}.GCSStorage') as storage_class:
        handler = storage_class.return_value
        handler.get_bucket_key.side_effect = _parse_uri
        yield storage_class, handler


@pytest.fixture
def azure_handler():
    with patch(f'{CLOUD_STORAGE}.AzureBlobStorage') as storage_class:
        handler = storage_class.return_value
        handler.get_bucket_key.side_effect = _parse_uri
        yield storage_class, handler


def _parse_uri(value: str):
    bucket, _, key = value.split('://', 1)[1].partition('/')
    return bucket, key


class TestTypes:
    def test_file_storage_types(self):
        assert is_file_storage_type('aws_s3')
        assert is_file_storage_type(DataSourceType.GCS)
        assert is_file_storage_type('azure_blob_storage')
        assert not is_file_storage_type('postgres')
        assert not is_file_storage_type('unknown')
        assert not is_file_storage_type(None)


class TestConfigValidation:
    def test_build_each_type(self):
        assert isinstance(
            build_file_storage_config('aws_s3', {'bucket_name': 'b'}),
            S3FileStorageConfig,
        )
        assert isinstance(
            build_file_storage_config('gcs', {'bucket_name': 'b'}),
            GCSFileStorageConfig,
        )
        assert isinstance(
            build_file_storage_config(
                'azure_blob_storage',
                {'container_name': 'c', 'account_url': AZURE_URL},
            ),
            AzureBlobStorageConfig,
        )

    def test_sql_type_rejected(self):
        with pytest.raises(ValueError, match='not a file storage'):
            build_file_storage_config('postgres', {'bucket_name': 'b'})

    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match='Invalid aws_s3 config'):
            build_file_storage_config('aws_s3', {'bucket_name': 'b', 'host': 'x'})

    def test_bucket_required(self):
        with pytest.raises(ValueError, match='bucket_name is required'):
            S3FileStorageConfig(bucket_name='  ')

    def test_s3_keys_must_be_paired(self):
        with pytest.raises(ValueError, match='together'):
            S3FileStorageConfig(bucket_name='b', aws_access_key_id='AKIA')

    def test_azure_partial_credentials_rejected(self):
        with pytest.raises(ValueError, match='together'):
            AzureBlobStorageConfig(
                container_name='c', account_url=AZURE_URL, client_id='id'
            )

    def test_azure_requires_account_url(self):
        with pytest.raises(ValueError, match='account_url is required'):
            AzureBlobStorageConfig(container_name='c', account_url='')

    def test_gcs_credentials_json_string_parsed(self):
        config = GCSFileStorageConfig(
            bucket_name='b', credentials_json='{"type": "service_account"}'
        )
        assert config.credentials_json == {'type': 'service_account'}

    def test_gcs_credentials_json_invalid(self):
        with pytest.raises(ValueError, match='not valid JSON'):
            GCSFileStorageConfig(bucket_name='b', credentials_json='{nope')

    def test_base_path_normalized(self):
        config = S3FileStorageConfig(bucket_name='b', base_path='/uploads//in/')
        assert config.base_path == 'uploads/in'

    def test_base_path_traversal_rejected(self):
        with pytest.raises(ValueError):
            S3FileStorageConfig(bucket_name='b', base_path='a/../b')


class TestUnsupportedTypes:
    def test_datasource_plugin_rejects_file_storage(self):
        with pytest.raises(ValueError, match='use FileStoragePlugin'):
            DatasourcePlugin(DataSourceType.AWS_S3, S3FileStorageConfig('b'))

    def test_file_storage_plugin_rejects_sql_config(self):
        with pytest.raises(ValueError, match='use DatasourcePlugin'):
            FileStoragePlugin(PostgresConfig('h', 5432, 'db', 'u', 'p'))


class TestProviderWiring:
    def test_s3_credentials_passed(self, s3_handler):
        storage_class, _ = s3_handler
        FileStoragePlugin(
            S3FileStorageConfig(
                bucket_name='b',
                aws_access_key_id='id',
                aws_secret_access_key='secret',
                region_name='us-east-1',
            )
        )
        storage_class.assert_called_once_with(
            aws_access_key_id='id',
            aws_secret_access_key='secret',
            region_name='us-east-1',
        )

    def test_gcs_credentials_passed(self, gcs_handler):
        storage_class, _ = gcs_handler
        FileStoragePlugin(
            GCSFileStorageConfig(
                bucket_name='b', project_id='p', credentials_json={'type': 'sa'}
            )
        )
        storage_class.assert_called_once_with(
            credentials_info={'type': 'sa'}, project_id='p'
        )

    def test_gcs_default_credentials(self, gcs_handler):
        storage_class, _ = gcs_handler
        FileStoragePlugin(GCSFileStorageConfig(bucket_name='b'))
        storage_class.assert_called_once_with()

    def test_azure_credentials_passed(self, azure_handler):
        storage_class, _ = azure_handler
        FileStoragePlugin(
            AzureBlobStorageConfig(container_name='c', account_url=AZURE_URL)
        )
        storage_class.assert_called_once_with(account_url=AZURE_URL)


class TestConnection:
    async def test_success(self, s3_handler):
        _, handler = s3_handler
        handler.list_files.return_value = ([], False)
        plugin = FileStoragePlugin(S3FileStorageConfig('b', base_path='in'))
        assert await plugin.test_connection() is True
        handler.list_files.assert_called_once_with('b', 'in', 1, 1)

    async def test_failure(self, gcs_handler):
        _, handler = gcs_handler
        handler.list_files.side_effect = Exception('bucket missing')
        plugin = FileStoragePlugin(GCSFileStorageConfig('b'))
        assert await plugin.test_connection() is False


class TestUploadDownload:
    @pytest.mark.parametrize(
        'fixture, config, uri',
        [
            ('s3_handler', S3FileStorageConfig('bkt'), 's3://bkt/dir/a.txt'),
            ('gcs_handler', GCSFileStorageConfig('bkt'), 'gs://bkt/dir/a.txt'),
            (
                'azure_handler',
                AzureBlobStorageConfig('bkt', AZURE_URL),
                'azure://bkt/dir/a.txt',
            ),
        ],
    )
    def test_upload_returns_full_uri(self, request, fixture, config, uri):
        _, handler = request.getfixturevalue(fixture)
        plugin = FileStoragePlugin(config)
        assert plugin.upload_file(b'hi', '/dir/a.txt', 'text/plain') == uri
        handler.save_small_file.assert_called_once_with(
            b'hi', 'bkt', 'dir/a.txt', 'text/plain', False
        )

    def test_upload_joins_base_path(self, s3_handler):
        _, handler = s3_handler
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt', base_path='uploads/'))
        assert plugin.upload_file(b'x', 'a.txt') == 's3://bkt/uploads/a.txt'

    def test_upload_rejects_traversal(self, s3_handler):
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt', base_path='uploads'))
        with pytest.raises(ValueError):
            plugin.upload_file(b'x', '../secrets.txt')

    def test_upload_rejects_empty_path(self, s3_handler):
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt'))
        with pytest.raises(ValueError, match='path is required'):
            plugin.upload_file(b'x', '/')

    def test_roundtrip(self, s3_handler):
        _, handler = s3_handler
        stored = {}
        handler.save_small_file.side_effect = (
            lambda content, bucket, key, *_: stored.__setitem__((bucket, key), content)
        )
        handler.get_file.side_effect = lambda bucket, key: stored[(bucket, key)]
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt', base_path='in'))

        uri = plugin.upload_file(b'payload', 'docs/a.pdf', 'application/pdf')
        assert plugin.download_file(uri) == b'payload'
        assert plugin.download_file('docs/a.pdf') == b'payload'

    def test_download_wrong_bucket(self, s3_handler):
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt'))
        with pytest.raises(ValueError, match='does not match'):
            plugin.download_file('s3://other/a.txt')

    def test_download_wrong_scheme(self, s3_handler):
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt'))
        with pytest.raises(ValueError, match='Expected a s3://'):
            plugin.download_file('gs://bkt/a.txt')

    def test_download_outside_base_path(self, s3_handler):
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt', base_path='in'))
        with pytest.raises(ValueError, match='outside'):
            plugin.download_file('s3://bkt/other/a.txt')
        with pytest.raises(ValueError, match='outside'):
            plugin.download_file('s3://bkt/inside/a.txt')

    def test_download_not_found_propagates(self, s3_handler):
        _, handler = s3_handler
        handler.get_file.side_effect = CloudStorageFileNotFoundError('bkt', 'a')
        plugin = FileStoragePlugin(S3FileStorageConfig('bkt'))
        with pytest.raises(CloudStorageFileNotFoundError):
            plugin.download_file('a')


def test_gcs_storage_accepts_credentials_info():
    from flo_cloud.gcp import gcs

    with (
        patch.object(
            gcs.service_account.Credentials, 'from_service_account_info'
        ) as from_info,
        patch.object(gcs.storage, 'Client') as client,
    ):
        credentials = MagicMock()
        from_info.return_value = credentials
        storage = gcs.GCSStorage(credentials_info={'project_id': 'from-sa'})
        client.assert_called_once_with(project='from-sa', credentials=credentials)
        assert storage.project_id == 'from-sa'
