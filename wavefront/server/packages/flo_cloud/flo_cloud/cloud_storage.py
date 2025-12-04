from io import BytesIO
from typing import Union, List, Tuple, Optional
from .aws.s3 import S3Storage
from .gcp.gcs import GCSStorage
from ._types import CloudStorageHandler, CloudProvider


class CloudStorageFactory:
    """Factory class to create appropriate cloud storage handler"""

    @staticmethod
    def get_handler(
        provider: Union[str, CloudProvider], **credentials
    ) -> CloudStorageHandler:
        """
        Create and return appropriate cloud storage handler based on provider

        Args:
            provider: Cloud provider (either string or CloudProvider enum)
            **credentials: Keyword arguments for provider-specific credentials

        Returns:
            CloudStorageHandler: Appropriate handler instance

        Raises:
            ValueError: If provider is not supported
        """
        if isinstance(provider, str):
            provider = CloudProvider(provider.lower())

        if provider == CloudProvider.AWS:
            return S3Storage()
        elif provider == CloudProvider.GCP:
            return GCSStorage()
        else:
            raise ValueError(f'Unsupported cloud provider: {provider}')


class CloudStorageManager:
    """Manager class to handle cloud storage operations"""

    def __init__(self, provider: Union[str, CloudProvider], **credentials):
        """
        Initialize storage manager with specified provider

        Args:
            provider: Cloud provider (either string or CloudProvider enum)
            **credentials: Provider-specific credentials
        """
        self.handler = CloudStorageFactory.get_handler(provider, **credentials)
        if isinstance(provider, str):
            provider = CloudProvider(provider.lower())
        self.provider = provider

    def _convert_to_valid_type(self, type: str) -> str:
        """
        Convert a generic type (get, put, post) to the provider-specific operation string.

        Args:
            type: The generic operation type ('get', 'put', 'post')
            provider: The cloud provider (CloudProvider.AWS or CloudProvider.GCP)

        Returns:
            str: The provider-specific operation string

        Raises:
            ValueError: If the type or provider is not supported
        """
        type = type.lower()
        if self.provider == CloudProvider.AWS:
            if type == 'get' or type == 'get_object':
                return 'get_object'
            elif type == 'put' or type == 'put_object':
                return 'put_object'
            elif type == 'post' or type == 'post_object':
                return 'post_object'
        elif self.provider == CloudProvider.GCP:
            if type == 'get_object' or type == 'get':
                return 'GET'
            elif type == 'put_object' or type == 'put':
                return 'PUT'
            elif type == 'post_object' or type == 'post':
                return 'POST'
        raise ValueError(f"Unsupported type '{type}' for provider '{self.provider}'")

    def read_file(self, bucket_name: str, file_path: str) -> BytesIO:
        """
        Read file from cloud storage

        Args:
            bucket_name: Name of the bucket
            file_path: Path to the file in bucket

        Returns:
            BytesIO: File contents as a buffer
        """
        return self.handler.get_file(bucket_name, file_path)

    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Save large file to cloud storage using streaming/multipart upload.

        Args:
            data: File data in bytes
            bucket_name: Name of the storage bucket
            key: Object key/path for the file in the bucket
            content_type: MIME type of the file (e.g., 'image/jpeg', 'application/pdf').
                         If None, the cloud provider will use its default.

        Returns:
            None
        """
        self.handler.save_large_file(data, bucket_name, key, content_type)

    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Save small file to cloud storage using direct upload.

        Args:
            file_content: File content in bytes
            bucket_name: Name of the storage bucket
            key: Object key/path for the file in the bucket
            content_type: MIME type of the file (e.g., 'image/jpeg', 'application/pdf').
                         If None, the cloud provider will use its default.

        Returns:
            None
        """
        self.handler.save_small_file(file_content, bucket_name, key, content_type)

    def file_protocol(self) -> str:
        return (
            's3' if self.provider == 'aws' else 'gs' if self.provider == 'gcp' else None
        )

    def get_bucket_key(self, value) -> str:
        return self.handler.get_bucket_key(value)

    def generate_presigned_url(
        self, bucket_name: str, key: str, type: str, expiresIn: int = 300
    ) -> str:
        try:
            valid_type = self._convert_to_valid_type(type)
            return self.handler.generate_presigned_url(
                bucket_name, key, valid_type, expiresIn
            )
        except Exception as e:
            raise e

    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """
        List files in cloud storage bucket with prefix filtering and pagination.

        Args:
            bucket_name (str): Name of the bucket
            prefix (str): Prefix to filter files
            page_size (int): Number of files per page (default: 50)
            page_number (int): Which page to retrieve, 1-based (default: 1)

        Returns:
            Tuple[List[str], bool]: (list of file keys/paths, has_next_page)

        Raises:
            Exception: If listing fails
        """
        return self.handler.list_files(bucket_name, prefix, page_size, page_number)

    def delete_file(self, bucket_name: str, file_path: str) -> None:
        """
        Delete file from cloud storage
        Args:
            bucket_name: Name of the bucket
            file_path: Path to the file in bucket
        """
        return self.handler.delete_file(bucket_name, file_path)
