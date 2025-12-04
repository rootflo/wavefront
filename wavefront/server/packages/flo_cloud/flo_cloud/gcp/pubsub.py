import os
import json
from typing import List
from google.cloud import pubsub_v1
from .._types import MessageQueue, MessageQueueDict

gcp_project_id = os.getenv('GCP_PROJECT_ID')
gcp_pubsub_subscription_id = os.getenv('GCP_PUBSUB_SUBSCRIPTION_ID')
gcp_pubsub_topic_id = os.getenv('GCP_PUBSUB_TOPIC_ID')


class PubSubQueue(MessageQueue):
    def __init__(self):
        self.project_id = gcp_project_id
        self.subscription_path = (
            f'projects/{self.project_id}/subscriptions/{gcp_pubsub_subscription_id}'
        )
        self.subscriber = pubsub_v1.SubscriberClient()
        self.publisher = pubsub_v1.PublisherClient()

    def delete_message(self, ack_id: str):
        try:
            self.subscriber.acknowledge(
                request={'subscription': self.subscription_path, 'ack_ids': [ack_id]}
            )
        except Exception as e:
            raise e

    def receive_messages(
        self, max_messages=10, wait_time_sec=20
    ) -> List[MessageQueueDict] | None:
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

    def add_message(
        self,
        message_body: dict,
        topic_name_or_queue_url: str | None = None,
        **attributes,
    ):
        try:
            if not topic_name_or_queue_url:
                topic_name_or_queue_url = gcp_pubsub_topic_id

            topic_path = f'projects/{self.project_id}/topics/{topic_name_or_queue_url}'

            message_data = json.dumps(message_body).encode('utf-8')

            # Publish with optional attributes
            future = self.publisher.publish(
                topic_path,
                message_data,
                **attributes,  # Can include custom attributes like {"source": "api", "version": "1.0"}
            )

            message_id = future.result()
            return message_id

        except Exception as e:
            raise e
