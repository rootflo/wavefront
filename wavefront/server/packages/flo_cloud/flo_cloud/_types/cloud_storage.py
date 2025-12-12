from abc import ABC, abstractmethod
from typing import List, Tuple, Optional


class CloudStorageHandler(ABC):
    """Abstract base class for cloud storage operations"""

    @abstractmethod
    def get_file(self, bucket_name: str, file_path: str) -> bytes:
        """
        Abstract method to get file from bucket and return as buffer

        Args:
            bucket_name (str): Name of the bucket
            file_path (str): Path to the file in bucket

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Save large file to cloud storage using streaming/multipart upload.

        Use this method for large files that benefit from streaming uploads
        and automatic multipart handling to optimize memory usage.

        Args:
            data: File data in bytes
            bucket_name: Name of the storage bucket
            key: Object key/path for the file in the bucket
            content_type: MIME type of the file (e.g., 'image/jpeg', 'application/pdf').
                         If None, the cloud provider will use its default.

        Raises:
            Exception: If upload fails
        """
        pass

    @abstractmethod
    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Save small file to cloud storage using direct upload.

        Use this method for small files that can be uploaded efficiently
        in a single operation without streaming.

        Args:
            file_content: File content in bytes
            bucket_name: Name of the storage bucket
            key: Object key/path for the file in the bucket
            content_type: MIME type of the file (e.g., 'image/jpeg', 'application/pdf').
                         If None, the cloud provider will use its default.

        Raises:
            Exception: If upload fails
        """
        pass

    @abstractmethod
    def get_bucket_key(self, value: str):
        """ """
        pass

    @abstractmethod
    def generate_presigned_url(
        self, bucket_name: str, key: str, type: str, expiresIn: int = 300
    ) -> str:
        """ """
        pass

    @abstractmethod
    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """
        List files in a bucket with prefix filtering and pagination.

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
        pass
