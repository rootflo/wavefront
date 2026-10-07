from typing import Union, List, Tuple, Optional, IO, ContextManager, Mapping, Iterable

from .aws.s3 import S3Storage
from .gcp.gcs import GCSStorage
from .azure.blob_storage import AzureBlobStorage
from ._types import CloudProvider


class CloudStorageManager:
    """Facade over S3 / GCS / Azure blob storage."""

    def __init__(self, provider: Union[str, CloudProvider], **credentials):
        """Build a manager for ``provider`` (enum or name string)."""
        if isinstance(provider, str):
            provider = CloudProvider(provider.lower())
        self.provider = provider

        if provider == CloudProvider.AWS:
            self.handler = S3Storage(**_filter_creds(credentials, _AWS_CREDENTIAL_KEYS))
        elif provider == CloudProvider.GCP:
            self.handler = GCSStorage()
        elif provider == CloudProvider.AZURE:
            self.handler = AzureBlobStorage(
                **_filter_creds(credentials, _AZURE_CREDENTIAL_KEYS)
            )
        else:
            raise ValueError(f'Unsupported cloud provider: {provider}')

    # --- Read / list ---

    def read_file(self, bucket_name: str, file_path: str) -> bytes:
        """Return object bytes from ``bucket_name`` / ``file_path``."""
        return self.handler.get_file(bucket_name, file_path)

    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """Return ``(keys, has_next_page)`` for ``prefix`` (1-based pages)."""
        return self.handler.list_files(bucket_name, prefix, page_size, page_number)

    # --- Write ---

    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
        disable_cache: bool = False,
    ) -> None:
        """Upload via a single put. ``disable_cache`` forces fresh reads after overwrite."""
        self.handler.save_small_file(
            file_content, bucket_name, key, content_type, disable_cache
        )

    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """Upload via streaming / multipart."""
        self.handler.save_large_file(data, bucket_name, key, content_type)

    def open_text_writer(
        self, bucket_name: str, key: str, content_type: Optional[str] = None
    ) -> ContextManager[IO[str]]:
        """Context manager for incremental text writes (streamed on GCS, buffered on S3)."""
        return self.handler.open_text_writer(bucket_name, key, content_type)

    # --- Delete ---

    def delete_file(self, bucket_name: str, file_path: str) -> None:
        """Delete ``file_path`` from ``bucket_name``."""
        return self.handler.delete_file(bucket_name, file_path)

    # --- URLs / metadata ---

    def generate_presigned_url(
        self,
        bucket_name: str,
        key: str,
        operation: str,
        expires_in: int = 300,
    ) -> str:
        """Presigned URL for ``operation`` (get/put/post); expires in ``expires_in`` seconds."""
        valid_operation = self._convert_to_valid_type(operation)
        return self.handler.generate_presigned_url(
            bucket_name, key, valid_operation, expires_in
        )

    def file_protocol(self) -> Optional[str]:
        """URI scheme for this provider (``s3``, ``gs``, or ``azure``)."""
        return _FILE_PROTOCOLS.get(self.provider)

    def get_bucket_key(self, value) -> str:
        """Normalize a path/URI to the provider's object key."""
        return self.handler.get_bucket_key(value)

    # --- Private ---

    def _convert_to_valid_type(self, operation: str) -> str:
        """Map a generic get/put/post name to the provider's API operation string."""
        ops = _OPERATION_MAP.get(self.provider)
        if ops is None:
            raise ValueError(
                f"Unsupported operation '{operation}' for provider '{self.provider}'"
            )
        key = operation.lower()
        try:
            return ops[key]
        except KeyError:
            raise ValueError(
                f"Unsupported operation '{operation}' for provider '{self.provider}'"
            ) from None


# --- Module private ---

_AWS_CREDENTIAL_KEYS = (
    'aws_access_key_id',
    'aws_secret_access_key',
    'region_name',
)
_AZURE_CREDENTIAL_KEYS = (
    'account_url',
    'client_id',
    'client_secret',
    'tenant_id',
)

_FILE_PROTOCOLS: Mapping[CloudProvider, str] = {
    CloudProvider.AWS: 's3',
    CloudProvider.GCP: 'gs',
    CloudProvider.AZURE: 'azure',
}

_HTTP_OPS = {
    'get': 'GET',
    'get_object': 'GET',
    'put': 'PUT',
    'put_object': 'PUT',
    'post': 'POST',
    'post_object': 'POST',
}

_OPERATION_MAP: Mapping[CloudProvider, Mapping[str, str]] = {
    CloudProvider.AWS: {
        'get': 'get_object',
        'get_object': 'get_object',
        'put': 'put_object',
        'put_object': 'put_object',
        'post': 'post_object',
        'post_object': 'post_object',
    },
    CloudProvider.GCP: _HTTP_OPS,
    CloudProvider.AZURE: _HTTP_OPS,
}


def _filter_creds(
    credentials: Mapping[str, object], allowed_keys: Iterable[str]
) -> dict:
    return {
        k: v
        for k, v in credentials.items()
        if k in allowed_keys and v not in (None, '')
    }
