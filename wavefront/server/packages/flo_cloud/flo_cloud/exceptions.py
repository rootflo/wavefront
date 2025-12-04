"""
Custom exceptions for flo_cloud package
"""


class CloudStorageError(Exception):
    """Base exception for cloud storage operations"""

    pass


class CloudStorageFileNotFoundError(CloudStorageError):
    """Exception raised when a file is not found in cloud storage"""

    def __init__(self, bucket_name: str, file_path: str, message: str = None):
        self.bucket_name = bucket_name
        self.file_path = file_path
        if message is None:
            message = f"File not found in bucket '{bucket_name}' at path '{file_path}'"
        super().__init__(message)
