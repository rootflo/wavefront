import logging

from .blob_storage import AzureBlobStorage
from .storage_queue import StorageQueue
from .key_vault import AzureKMS

logging.getLogger('azure').setLevel(logging.WARNING)

__all__ = ['AzureBlobStorage', 'AzureKMS', 'StorageQueue']
