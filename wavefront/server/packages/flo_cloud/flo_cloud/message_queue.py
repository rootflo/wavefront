from ._types import CloudProvider, MessageQueue
from .aws.sqs import SQSQueue
from .gcp.pubsub import PubSubQueue


class MessageQueueManager(MessageQueue):
    def __init__(self, cloud_provider: str):
        self.cloud_provider = cloud_provider
        self.message_queue_client = self.__get_message_queue_client()

    def __get_message_queue_client(self) -> MessageQueue:
        if self.cloud_provider == CloudProvider.AWS.value:
            return SQSQueue()
        elif self.cloud_provider == CloudProvider.GCP.value:
            return PubSubQueue()
        else:
            raise ValueError(f'Unsupported cloud provider: {self.cloud_provider}')

    def receive_messages(self, max_messages=10, wait_time_sec=20):
        return self.message_queue_client.receive_messages(max_messages, wait_time_sec)

    def delete_message(self, ack_id: str):
        return self.message_queue_client.delete_message(ack_id)

    def add_message(
        self, message_body: dict, topic_name_or_queue_url: str | None = None
    ) -> str:
        return self.message_queue_client.add_message(
            message_body, topic_name_or_queue_url
        )
