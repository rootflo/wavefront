from datetime import datetime, timedelta, UTC
import io
from itertools import islice
from google.cloud import storage
from google.cloud.exceptions import NotFound
from typing import Optional, List, Tuple
from .._types import CloudStorageHandler
from ..exceptions import CloudStorageFileNotFoundError
import re
from re import Match


class GCSStorage(CloudStorageHandler):
    """Google Cloud Storage implementation"""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize GCP client

        Args:
            credentials_path: Path to GCP credentials JSON file (optional)
        """
        if credentials_path:
            self.client = storage.Client.from_service_account_json(credentials_path)
        else:
            self.client = storage.Client()

    def get_file(self, bucket_name: str, file_path: str) -> bytes:
        """
        Get file from GCS bucket and return as buffer

        Args:
            bucket_name (str): Name of the GCS bucket
            file_path (str): Path to the file in bucket

        Returns:
            File content as bytes

        Raises:
            CloudStorageFileNotFoundError: If file not found
            Exception: If other errors occur
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            return blob.download_as_bytes()
        except NotFound:
            # GCS-specific NotFound exception
            raise CloudStorageFileNotFoundError(bucket_name, file_path)
        except Exception as e:
            raise Exception(f'Error reading file from GCS: {str(e)}')

    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """GCS implementation of large file upload using upload_from_file with streaming."""
        try:
            if not bucket_name:
                raise ValueError('bucket_name cannot be None or empty')
            if not key:
                raise ValueError('key cannot be None or empty')
            if data is None:
                raise ValueError('data cannot be None')

            fileobj = io.BytesIO(data)
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(key)

            if content_type is not None:
                blob.upload_from_file(fileobj, content_type=content_type)
            else:
                blob.upload_from_file(fileobj)
        except Exception as e:
            raise Exception(f'Error uploading large file to GCS: {str(e)}')

    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """GCS implementation of small file upload using upload_from_string."""
        try:
            if not bucket_name:
                raise ValueError('bucket_name cannot be None or empty')
            if not key:
                raise ValueError('key cannot be None or empty')
            if file_content is None:
                raise ValueError('file_content cannot be None')

            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(key)

            if content_type is not None:
                blob.upload_from_string(file_content, content_type=content_type)
            else:
                blob.upload_from_string(file_content)
        except Exception as e:
            raise Exception(f'Error uploading small file to GCS: {str(e)}')

    def get_bucket_key(self, value: str):
        match: Optional[Match[str]] = re.match(r'gs://([^/]+)/(.+)', value)
        if not match:
            raise ValueError('Invalid GCS URL format')
        bucket_name = match.group(1)
        key = match.group(2)
        return bucket_name, key

    def generate_presigned_url(
        self, bucket_name: str, key: str, type: str, expiresIn: int = 300
    ) -> str:
        """
        Generate a presigned URL for a file in a GCS bucket.

        Args:
            bucket_name (str): Name of the GCS bucket
            key (str): Path to the file in the bucket
            type (str): HTTP method for the presigned URL (e.g., 'GET', 'PUT')
            expiresIn (int, optional): Expiration time in seconds (default: 300)

        Returns:
            str: Presigned URL

        Raises:
            Exception: If URL generation fails
        """
        try:
            if not bucket_name:
                raise ValueError('bucket_name cannot be None or empty')
            if not key:
                raise ValueError('key cannot be None or empty')
            if not type:
                raise ValueError('type cannot be None or empty')

            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(key)
            presigned_url = blob.generate_signed_url(
                version='v4',
                expiration=datetime.now(UTC) + timedelta(seconds=expiresIn),
                method=type,
            )
            return presigned_url
        except Exception as e:
            raise Exception(f'Error generating presigned URL for GCS: {str(e)}')

    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """
        List files in a GCS bucket with prefix filtering and pagination.
        Optimized to use server-side pagination instead of client-side skipping.

        Args:
            bucket_name (str): Name of the GCS bucket
            prefix (str): Prefix to filter files
            page_size (int): Number of files per page (default: 50)
            page_number (int): Which page to retrieve, 1-based (default: 1)

        Returns:
            Tuple[List[str], bool]: (list of blob names, has_next_page)

        Raises:
            Exception: If listing fails
        """
        try:
            if page_number < 1:
                raise ValueError('page_number must be >= 1')
            if page_size < 1:
                raise ValueError('page_size must be >= 1')

            bucket = self.client.bucket(bucket_name)

            # Create an iterator for all matching blobs. The library handles API calls page by page.
            blobs_iterator = bucket.list_blobs(prefix=prefix)

            # Calculate the start and end index for the desired page
            start_index = (page_number - 1) * page_size
            # We fetch one extra item to check if there's a next page
            end_index = start_index + page_size + 1

            # Use islice to efficiently get only the items for our page.
            # It advances the iterator internally without pulling all data.
            page_slice = islice(blobs_iterator, start_index, end_index)

            # Convert the iterator slice to a list
            file_names = [blob.name for blob in page_slice]

            # Determine if there's a next page
            has_next_page = len(file_names) > page_size

            # Return only the requested page size
            if has_next_page:
                return file_names[:page_size], True
            else:
                return file_names, False

        except NotFound:
            raise Exception(f'Bucket {bucket_name} not found')
        except Exception as e:
            raise Exception(f'Error listing files from GCS: {str(e)}')

    def delete_file(self, bucket_name: str, file_path: str) -> None:
        """
        Delete file from GCS bucket
        Args:
            bucket_name: Name of the GCS bucket
            file_path: Path to the file in bucket
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            blob.delete()
        except Exception as e:
            raise Exception(f'Error deleting file from GCS: {str(e)}')
