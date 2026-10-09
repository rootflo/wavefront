from ._types import CloudProvider, MessageQueue, QueueSettings
from .aws.sqs import SQSQueue
from .azure.storage_queue import StorageQueue
from .gcp.pubsub import PubSubQueue


class MessageQueueManager(MessageQueue):
    def __init__(self, settings: QueueSettings):
        self.settings = settings
        self.message_queue_client = self.__get_message_queue_client()

    def __get_message_queue_client(self) -> MessageQueue:
        if self.settings.provider == CloudProvider.AWS.value:
            return SQSQueue(self.settings)
        elif self.settings.provider == CloudProvider.GCP.value:
            return PubSubQueue(self.settings)
        elif self.settings.provider == CloudProvider.AZURE.value:
            return StorageQueue(self.settings)
        else:
            raise ValueError(f'Unsupported cloud provider: {self.settings.provider}')

    def receive_messages(self, max_messages=10, wait_time_sec=20):
        return self.message_queue_client.receive_messages(max_messages, wait_time_sec)

    def delete_message(self, ack_id: str):
        return self.message_queue_client.delete_message(ack_id)

    def add_message(self, message_body: dict) -> str:
        return self.message_queue_client.add_message(message_body)
