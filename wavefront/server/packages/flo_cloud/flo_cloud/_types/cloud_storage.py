from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple, Optional, IO, ContextManager


@dataclass
class StorageObject:
    """One object from a listing, with what the provider's list call already returns about it."""

    key: str
    size: Optional[int] = None
    # S3 doesn't return the content type when listing, only on a HEAD; it stays None there.
    content_type: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass
class FolderListing:
    """One level of a bucket: the folders and objects directly under a prefix."""

    # Full prefixes of the immediate sub-folders, each ending in the delimiter.
    folders: List[str] = field(default_factory=list)
    files: List[StorageObject] = field(default_factory=list)
    # Pass back to get the next page; None on the last one.
    next_page_token: Optional[str] = None


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
        disable_cache: bool = False,
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
            disable_cache: If True, mark the object as non-cacheable
                         (Cache-Control: no-store) so that an overwrite at the
                         same key is read back immediately instead of serving a
                         previously cached generation.

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

    def list_folder(
        self,
        bucket_name: str,
        prefix: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        delimiter: str = '/',
    ) -> FolderListing:
        """
        List one level under ``prefix``: its immediate folders and the objects directly in it.

        Unlike ``list_files`` this does not descend into sub-folders, and it pages with the
        provider's own continuation token, so every page costs one list call however deep it is.

        Args:
            bucket_name: Name of the bucket
            prefix: Folder to list, ending in ``delimiter`` (or '' for the bucket root)
            page_size: Most objects to return in one page
            page_token: ``next_page_token`` from the previous page, or None for the first
            delimiter: What separates folder names in a key

        Returns:
            FolderListing for this page.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support folder listing'
        )

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

    @abstractmethod
    def open_text_writer(
        self, bucket_name: str, key: str, content_type: Optional[str] = None
    ) -> ContextManager[IO[str]]:
        """
        Open a text writer stream to cloud storage for incremental writes.

        Implementations should return a context manager that yields a file-like
        object opened in text mode. Data written to this object must be
        uploaded to the underlying storage when the context manager exits.
        """
        pass
