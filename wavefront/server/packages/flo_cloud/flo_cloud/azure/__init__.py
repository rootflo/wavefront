import logging

from .blob_storage import AzureBlobStorage
from .storage_queue import StorageQueue
from .key_vault import AzureKmsCipher, AzureKmsSigner

logging.getLogger('azure').setLevel(logging.WARNING)

__all__ = ['AzureBlobStorage', 'AzureKmsCipher', 'AzureKmsSigner', 'StorageQueue']
