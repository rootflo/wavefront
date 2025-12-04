from enum import Enum
from .kms import FloKMS
from .cloud_storage import CloudStorageHandler
from .message_queue import MessageQueue, MessageQueueDict


class CloudProvider(str, Enum):
    AWS = 'aws'
    GCP = 'gcp'
    AZURE = 'azure'


__all__ = [
    'CloudProvider',
    'FloKMS',
    'CloudStorageHandler',
    'MessageQueue',
    'MessageQueueDict',
]
