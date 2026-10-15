import asyncio
import logging
from typing import Optional

from flo_cloud._types import CloudProvider
from flo_cloud.cloud_storage import CloudStorageManager

from ..types import DataSourceType, FileStorageABC
from .config import (
    AzureBlobStorageConfig,
    FileStorageConfig,
    GCSFileStorageConfig,
    S3FileStorageConfig,
    build_file_storage_config,
    normalize_storage_path,
)

logger = logging.getLogger(__name__)

__all__ = [
    'AzureBlobStorageConfig',
    'FileStorageConfig',
    'FileStoragePlugin',
    'GCSFileStorageConfig',
    'S3FileStorageConfig',
    'build_file_storage_config',
]


class FileStoragePlugin(FileStorageABC):
    """Upload/download against one bucket (or container), under ``base_path``."""

    def __init__(self, config: FileStorageConfig):
        self.config = config
        if isinstance(config, S3FileStorageConfig):
            self.datasource_type = DataSourceType.AWS_S3
            self.bucket_name = config.bucket_name
            provider = CloudProvider.AWS
            credentials = {
                'aws_access_key_id': config.aws_access_key_id,
                'aws_secret_access_key': config.aws_secret_access_key,
                'region_name': config.region_name,
            }
        elif isinstance(config, GCSFileStorageConfig):
            self.datasource_type = DataSourceType.GCS
            self.bucket_name = config.bucket_name
            provider = CloudProvider.GCP
            credentials = {
                'credentials_info': config.credentials_json,
                'project_id': config.project_id,
            }
        elif isinstance(config, AzureBlobStorageConfig):
            self.datasource_type = DataSourceType.AZURE_BLOB_STORAGE
            self.bucket_name = config.container_name
            provider = CloudProvider.AZURE
            credentials = {
                'account_url': config.account_url,
                'client_id': config.client_id,
                'client_secret': config.client_secret,
                'tenant_id': config.tenant_id,
            }
        else:
            raise ValueError(
                f'{type(config).__name__} is not a file storage config; '
                'SQL datasources must use DatasourcePlugin'
            )

        self.base_path = config.base_path or ''
        self.storage = CloudStorageManager(provider, **credentials)
        self.protocol = self.storage.file_protocol()

    async def test_connection(self) -> bool:
        """Lists at most one object under ``base_path``, so the credentials need
        list permission there (e.g. s3:ListBucket) on top of read/write."""
        try:
            await asyncio.to_thread(
                self.storage.list_files, self.bucket_name, self.base_path, 1, 1
            )
            return True
        except Exception as e:
            logger.error(
                f'{self.datasource_type.value} connection test failed '
                f'for {self.bucket_name}: {e}'
            )
            return False

    def upload_file(
        self, file_content: bytes, path: str, content_type: Optional[str] = None
    ) -> str:
        key = self._key_for(path)
        self.storage.save_small_file(
            file_content, self.bucket_name, key, content_type=content_type
        )
        return self.uri_for(key)

    def download_file(self, path: str) -> bytes:
        return self.storage.read_file(self.bucket_name, self.resolve_key(path))

    def uri_for(self, key: str) -> str:
        return f'{self.protocol}://{self.bucket_name}/{key}'

    def resolve_key(self, path: str) -> str:
        """Key for ``path``: a full URI as-is, otherwise relative to ``base_path``.

        Either way the key must stay inside this datasource's bucket and
        ``base_path``.
        """
        if not isinstance(path, str) or not path.strip():
            raise ValueError('path is required')
        if '://' not in path:
            return self._key_for(path)

        prefix = f'{self.protocol}://'
        if not path.startswith(prefix):
            raise ValueError(f'Expected a {prefix} URI, got: {path}')
        bucket_name, key = self.storage.get_bucket_key(path)
        if bucket_name != self.bucket_name:
            raise ValueError(
                f'URI bucket {bucket_name!r} does not match datasource bucket '
                f'{self.bucket_name!r}'
            )
        key = normalize_storage_path(key)
        if self.base_path and not (
            key == self.base_path or key.startswith(f'{self.base_path}/')
        ):
            raise ValueError(f'Path is outside the datasource base path: {path}')
        if not key:
            raise ValueError('path is required')
        return key

    def _key_for(self, path: str) -> str:
        relative = normalize_storage_path(path)
        if not relative:
            raise ValueError('path is required')
        return f'{self.base_path}/{relative}' if self.base_path else relative
