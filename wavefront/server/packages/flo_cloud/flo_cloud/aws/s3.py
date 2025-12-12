from itertools import islice
import boto3
import io
from typing import Optional, List, Tuple
from botocore.exceptions import ClientError
from .._types import CloudStorageHandler
from ..exceptions import CloudStorageFileNotFoundError
import re


class S3Storage(CloudStorageHandler):
    """AWS S3 implementation"""

    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        """
        Initialize AWS client

        Args:
            aws_access_key_id: AWS access key ID (optional)
            aws_secret_access_key: AWS secret access key (optional)
            region_name: AWS region name (optional)
        """
        self.s3_client = boto3.client('s3')

    def get_file(self, bucket_name: str, file_path: str) -> bytes:
        """
        Get file from S3 bucket and return as buffer

        Args:
            bucket_name (str): Name of the S3 bucket
            file_path (str): Path to the file in bucket

        Returns:
            File content as bytes

        Raises:
            CloudStorageFileNotFoundError: If file not found
            Exception: If other errors occur
        """
        try:
            s3_response = self.s3_client.get_object(Bucket=bucket_name, Key=file_path)
            file_content = s3_response['Body'].read()

            return file_content
        except ClientError as e:
            # Check if the error is specifically "NoSuchKey" or "NoSuchBucket"
            if e.response['Error']['Code'] in ['NoSuchKey', 'NoSuchBucket']:
                raise CloudStorageFileNotFoundError(bucket_name, file_path)
            else:
                # Re-raise other ClientError exceptions
                raise Exception(f'Error reading file from S3: {str(e)}')
        except Exception as e:
            raise Exception(f'Error reading file from S3: {str(e)}')

    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """S3 implementation of large file upload using upload_fileobj."""
        try:
            fileobj = io.BytesIO(data)
            extra_args = {}
            if content_type is not None:
                extra_args['ContentType'] = content_type

            if extra_args:
                self.s3_client.upload_fileobj(
                    fileobj, bucket_name, key, ExtraArgs=extra_args
                )
            else:
                self.s3_client.upload_fileobj(fileobj, bucket_name, key)
        except Exception as e:
            raise Exception(f'Error uploading large file to S3: {str(e)}')

    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """S3 implementation of small file upload using put_object."""
        try:
            kwargs = {'Bucket': bucket_name, 'Key': key, 'Body': file_content}
            if content_type is not None:
                kwargs['ContentType'] = content_type

            self.s3_client.put_object(**kwargs)
        except Exception as e:
            raise Exception(f'Error uploading small file to S3: {str(e)}')

    def get_bucket_key(self, value: str):
        match = re.match(r's3://([^/]+)/(.+)', value)
        bucket_name = match.group(1)
        key = match.group(2)
        return bucket_name, key

    def generate_presigned_url(
        self, bucket_name: str, key: str, type: str = 'get_object', expiresIn: int = 300
    ) -> str:
        """
        Generate a presigned URL for an S3 object.

        Args:
            bucket_name (str): Name of the S3 bucket
            key (str): Key of the object in the bucket
            type (str): Type of operation (e.g., 'get_object', 'put_object')
            expiresIn (int): Expiration time in seconds (default: 300)

        Returns:
            str: Presigned URL

        Raises:
            Exception: If URL generation fails
        """
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                type,
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=expiresIn,
            )
            return presigned_url
        except Exception as e:
            raise Exception(f'Error generating presigned URL for S3: {str(e)}')

    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """
        List files in an S3 bucket with prefix filtering and pagination.
        Optimized to use server-side pagination efficiently.

        Args:
            bucket_name (str): Name of the S3 bucket
            prefix (str): Prefix to filter files
            page_size (int): Number of files per page (default: 50)
            page_number (int): Which page to retrieve, 1-based (default: 1)

        Returns:
            Tuple[List[str], bool]: (list of object keys, has_next_page)

        Raises:
            Exception: If listing fails
        """
        try:
            if page_number < 1:
                raise ValueError('page_number must be >= 1')
            if page_size < 1:
                raise ValueError('page_size must be >= 1')

            paginator = self.s3_client.get_paginator('list_objects_v2')

            # Create a flat, memory-efficient iterator over all objects
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
            item_iterator = page_iterator.search('Contents')

            # Calculate the start and end index for the desired page slice
            start_index = (page_number - 1) * page_size
            # Fetch one extra item to check if there is a next page
            end_index = start_index + page_size + 1

            # Use islice to efficiently advance the iterator and get only our page
            page_slice = islice(item_iterator, start_index, end_index)

            # Extract the 'Key' from the dictionaries in the slice
            file_keys = [item['Key'] for item in page_slice if item is not None]

            # Determine if there's a next page
            has_next_page = len(file_keys) > page_size

            # Return only the requested page size
            if has_next_page:
                return file_keys[:page_size], True
            else:
                return file_keys, False

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                raise Exception(f'Bucket {bucket_name} not found')
            else:
                raise Exception(f'Error listing files from S3: {str(e)}')
        except Exception as e:
            raise Exception(f'Error listing files from S3: {str(e)}')

    def delete_file(self, bucket_name: str, file_path: str) -> None:
        """
        Delete file from S3 bucket
        Args:
            bucket_name: Name of the S3 bucket
            file_path: Path to the file in bucket
        """
        try:
            self.s3_client.delete_object(Bucket=bucket_name, Key=file_path)
        except Exception as e:
            raise Exception(f'Error deleting file from S3: {str(e)}')
