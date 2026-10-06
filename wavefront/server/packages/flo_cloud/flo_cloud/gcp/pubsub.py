import json
from typing import List

from google.cloud import pubsub_v1

from .._types import MessageQueue, MessageQueueDict, QueueSettings


class PubSubQueue(MessageQueue):
    def __init__(self, settings: QueueSettings):
        if not settings.project_id:
            raise ValueError('project_id must be set for PubSubQueue')
        if not settings.target:
            raise ValueError('target (topic id) must be set for PubSubQueue')

        self.project_id = settings.project_id
        self.topic_id = settings.target
        self.subscription_path = (
            f'projects/{self.project_id}/subscriptions/{settings.subscription}'
            if settings.subscription
            else None
        )
        self.subscriber = pubsub_v1.SubscriberClient()
        self.publisher = pubsub_v1.PublisherClient()

    def delete_message(self, ack_id: str):
        if not self.subscription_path:
            raise ValueError('subscription must be set to delete messages')
        try:
            self.subscriber.acknowledge(
                request={'subscription': self.subscription_path, 'ack_ids': [ack_id]}
            )
        except Exception as e:
            raise e

    def receive_messages(
        self, max_messages=10, wait_time_sec=20
    ) -> List[MessageQueueDict]:
        if not self.subscription_path:
            raise ValueError('subscription must be set to receive messages')
        try:
            response = self.subscriber.pull(
                request={
                    'subscription': self.subscription_path,
                    'max_messages': max_messages,
                },
                timeout=wait_time_sec,
            )

            messages = []

            for received_msg in response.received_messages:
                data_str = received_msg.message.data.decode('utf-8')
                body = json.loads(data_str)
                messages.append(
                    MessageQueueDict(
                        body=body,
                        ack_id=received_msg.ack_id,
                        id=received_msg.message.message_id,
                    )
                )

            return messages
        except Exception as e:
            raise e

    def add_message(self, message_body: dict, **attributes) -> str:
        try:
            topic_path = f'projects/{self.project_id}/topics/{self.topic_id}'
            message_data = json.dumps(message_body).encode('utf-8')
            future = self.publisher.publish(
                topic_path,
                message_data,
                **attributes,
            )
            return future.result()
        except Exception as e:
            raise e
