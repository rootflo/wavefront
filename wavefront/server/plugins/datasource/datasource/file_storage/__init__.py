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
    'DATASOURCE_URI_PREFIX',
    'build_datasource_uri',
    'split_datasource_uri',
    'AzureBlobStorageConfig',
    'FileStorageConfig',
    'FileStoragePlugin',
    'GCSFileStorageConfig',
    'S3FileStorageConfig',
    'build_file_storage_config',
]


# Paths handed out by the API name the datasource rather than the bucket, so a
# stored path always leads back to the datasource (and its credentials) that
# owns it: datasource://<datasource_id>/<key relative to base_path>.
DATASOURCE_URI_PREFIX = 'datasource://'


def build_datasource_uri(datasource_id: str, path: str) -> str:
    relative = normalize_storage_path(path)
    if not relative:
        raise ValueError('path is required')
    return f'{DATASOURCE_URI_PREFIX}{datasource_id}/{relative}'


def split_datasource_uri(path: str) -> Optional[tuple[str, str]]:
    """``(datasource_id, key)`` for a ``datasource://`` path, None for a plain key."""
    if not isinstance(path, str) or not path.lower().startswith(DATASOURCE_URI_PREFIX):
        return None
    datasource_id, _, key = path[len(DATASOURCE_URI_PREFIX) :].partition('/')
    if not datasource_id or not key:
        raise ValueError(
            f'Expected {DATASOURCE_URI_PREFIX}<datasource_id>/<key>, got: {path}'
        )
    return datasource_id, key


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
        """Storage key for ``path``, a key relative to ``base_path``.

        Callers holding a ``datasource://`` path strip it with
        ``split_datasource_uri`` first, after checking the datasource id.
        """
        if not isinstance(path, str) or not path.strip():
            raise ValueError('path is required')
        if '://' in path:
            raise ValueError(
                f'Expected {DATASOURCE_URI_PREFIX}<datasource_id>/<key> or a key '
                f'relative to the base path, got: {path}'
            )
        return self._key_for(path)

    def _key_for(self, path: str) -> str:
        relative = normalize_storage_path(path)
        if not relative:
            raise ValueError('path is required')
        return f'{self.base_path}/{relative}' if self.base_path else relative
