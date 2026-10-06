import json
from typing import List

import boto3

from .._types import MessageQueue, MessageQueueDict, QueueSettings


class SQSQueue(MessageQueue):
    def __init__(self, settings: QueueSettings):
        if not settings.target:
            raise ValueError('target (queue URL) must be set for SQSQueue')
        self.sqs_client = boto3.client('sqs')
        self.queue_url = settings.target

    def receive_messages(
        self, max_messages=10, wait_time_sec=20, **kwargs
    ) -> List[MessageQueueDict]:
        try:
            response = self.sqs_client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_sec,
                VisibilityTimeout=kwargs.get('visibility_timeout', 300),
            )

            messages = []
            for message in response.get('Messages', []):
                body = json.loads(message['Body'])
                messages.append(
                    MessageQueueDict(
                        body=body,
                        ack_id=message['ReceiptHandle'],
                        id=message['MessageId'],
                    )
                )

            return messages
        except Exception as e:
            raise e

    def delete_message(self, ack_id: str):
        try:
            self.sqs_client.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=ack_id
            )
        except Exception as e:
            raise e

    def add_message(self, message_body: dict, **attributes) -> str:
        try:
            message_data = json.dumps(message_body)
            message_params = {
                'QueueUrl': self.queue_url,
                'MessageBody': message_data,
            }

            if attributes:
                message_attributes = {}
                for key, value in attributes.items():
                    message_attributes[key] = {
                        'StringValue': str(value),
                        'DataType': 'String',
                    }
                message_params['MessageAttributes'] = message_attributes

            response = self.sqs_client.send_message(**message_params)
            return response['MessageId']
        except Exception as e:
            raise e
