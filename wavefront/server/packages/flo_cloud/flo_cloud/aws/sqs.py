import os
from typing import List
import boto3
import json
from .._types import MessageQueue, MessageQueueDict

queue_url = os.getenv('QUEUE_URL')


class SQSQueue(MessageQueue):
    def __init__(self):
        self.sqs_client = boto3.client('sqs')
        self.queue_url = queue_url

    def receive_messages(
        self, max_messages=10, wait_time_sec=20, **kwargs
    ) -> List[MessageQueueDict] | None:
        try:
            response = self.sqs_client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_sec,
                VisibilityTimeout=kwargs.get('visibility_timeout', 300),
            )

            if 'Messages' not in response:
                return None

            messages = []
            for message in response['Messages']:
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

    def add_message(
        self, message_body: dict, topic_name_or_queue_url: str = None, **attributes
    ) -> str:
        try:
            # Use provided queue_url or fall back to default
            target_queue_url = topic_name_or_queue_url or self.queue_url

            message_data = json.dumps(message_body)

            # Prepare message parameters
            message_params = {'QueueUrl': target_queue_url, 'MessageBody': message_data}

            # Add message attributes if provided
            if attributes:
                message_attributes = {}
                for key, value in attributes.items():
                    message_attributes[key] = {
                        'StringValue': str(value),
                        'DataType': 'String',
                    }
                message_params['MessageAttributes'] = message_attributes

            # Send the message
            response = self.sqs_client.send_message(**message_params)

            return response['MessageId']

        except Exception as e:
            raise e
