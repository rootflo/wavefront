from enum import Enum

from .cloud_storage import CloudStorageHandler
from .kms import FloCipher, FloKMS, FloSigner
from .message_queue import MessageQueue, MessageQueueDict
from .settings import KmsKeySettings, QueueSettings


class CloudProvider(str, Enum):
    AWS = 'aws'
    GCP = 'gcp'
    AZURE = 'azure'


__all__ = [
    'CloudProvider',
    'FloKMS',
    'FloSigner',
    'FloCipher',
    'KmsKeySettings',
    'QueueSettings',
    'CloudStorageHandler',
    'MessageQueue',
    'MessageQueueDict',
]
