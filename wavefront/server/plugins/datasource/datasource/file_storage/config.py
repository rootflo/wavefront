import json
from dataclasses import dataclass
from typing import Any, Optional

from ..types import DataSourceType


def normalize_storage_path(path: Optional[str]) -> str:
    """Collapse slashes and reject ``.``/``..`` segments in an object key."""
    if path is None:
        return ''
    if not isinstance(path, str):
        raise ValueError('Storage path must be a string')
    if '\\' in path or any(ord(ch) < 32 for ch in path):
        raise ValueError(f'Invalid storage path: {path!r}')
    segments = [segment for segment in path.split('/') if segment]
    if any(segment in ('.', '..') for segment in segments):
        raise ValueError(f'Storage path may not contain "." or "..": {path!r}')
    return '/'.join(segments)


def _require(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} is required')


@dataclass
class S3FileStorageConfig:
    bucket_name: str
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    region_name: Optional[str] = None
    base_path: Optional[str] = None

    def __post_init__(self):
        _require(self.bucket_name, 'bucket_name')
        if bool(self.aws_access_key_id) != bool(self.aws_secret_access_key):
            raise ValueError(
                'aws_access_key_id and aws_secret_access_key must be provided together'
            )
        self.base_path = normalize_storage_path(self.base_path)


@dataclass
class GCSFileStorageConfig:
    bucket_name: str
    project_id: Optional[str] = None
    credentials_json: Optional[dict] = None
    base_path: Optional[str] = None

    def __post_init__(self):
        _require(self.bucket_name, 'bucket_name')
        if isinstance(self.credentials_json, str):
            if not self.credentials_json.strip():
                self.credentials_json = None
            else:
                try:
                    self.credentials_json = json.loads(self.credentials_json)
                except json.JSONDecodeError as e:
                    raise ValueError(f'credentials_json is not valid JSON: {e}')
        if self.credentials_json is not None and not isinstance(
            self.credentials_json, dict
        ):
            raise ValueError('credentials_json must be a JSON object')
        self.base_path = normalize_storage_path(self.base_path)


@dataclass
class AzureBlobStorageConfig:
    container_name: str
    account_url: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_id: Optional[str] = None
    base_path: Optional[str] = None

    def __post_init__(self):
        _require(self.container_name, 'container_name')
        _require(self.account_url, 'account_url')
        credentials = [self.client_id, self.client_secret, self.tenant_id]
        if any(credentials) and not all(credentials):
            raise ValueError(
                'client_id, client_secret and tenant_id must be provided together'
            )
        self.base_path = normalize_storage_path(self.base_path)


FileStorageConfig = S3FileStorageConfig | GCSFileStorageConfig | AzureBlobStorageConfig

FILE_STORAGE_CONFIG_CLASSES: dict[DataSourceType, type] = {
    DataSourceType.AWS_S3: S3FileStorageConfig,
    DataSourceType.GCS: GCSFileStorageConfig,
    DataSourceType.AZURE_BLOB_STORAGE: AzureBlobStorageConfig,
}


def build_file_storage_config(
    datasource_type: str | DataSourceType, config: dict
) -> FileStorageConfig:
    """Build the config for a file-storage type; ValueError on bad type/fields."""
    try:
        config_class = FILE_STORAGE_CONFIG_CLASSES[DataSourceType(datasource_type)]
    except (KeyError, ValueError):
        raise ValueError(
            f'{datasource_type} is not a file storage datasource type'
        ) from None
    if not isinstance(config, dict):
        raise ValueError('Datasource config must be a JSON object')
    try:
        return config_class(**config)
    except TypeError as e:
        raise ValueError(f'Invalid {datasource_type} config: {e}') from None
