import base64
import binascii
import json
import os
from typing import List

from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient

from .._types import MessageQueue, MessageQueueDict


def _decode_message(content: str):
    """Parse message content as JSON, falling back to base64-decode first.

    Event Grid delivers messages to Storage Queue as base64-encoded JSON.
    Messages we send ourselves are plain JSON.
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            return json.loads(base64.b64decode(content).decode('utf-8'))
        except (binascii.Error, UnicodeDecodeError) as e:
            raise ValueError(
                f'Message content is neither valid JSON nor base64-encoded JSON: {e}'
            )


class StorageQueue(MessageQueue):
    """Azure Storage Queue implementation."""

    def __init__(self):
        account_url = os.environ.get('AZURE_STORAGE_QUEUE_URL')
        if not account_url:
            raise ValueError('AZURE_STORAGE_QUEUE_URL env var must be set')

        queue_name = os.environ.get('AZURE_STORAGE_QUEUE_NAME')
        if not queue_name:
            raise ValueError('AZURE_STORAGE_QUEUE_NAME env var must be set')

        self._account_url = account_url
        self._queue_name = queue_name
        self._credential = DefaultAzureCredential()
        self._client = QueueClient(
            account_url=account_url,
            queue_name=queue_name,
            credential=self._credential,
            message_encode_policy=None,
            message_decode_policy=None,
        )
        # Maps pop_receipt (ack_id) -> message_id for delete
        self._pending: dict[str, str] = {}

    def receive_messages(
        self, max_messages=10, wait_time_sec=20
    ) -> List[MessageQueueDict]:
        """Receive messages from Azure Storage Queue.

        Note: Azure Storage Queue does not support long-polling. This method
        returns immediately, potentially with an empty list. The `wait_time_sec`
        parameter is repurposed as the visibility timeout, controlling how long
        received messages remain hidden from other consumers.

        Args:
            max_messages: Maximum number of messages to receive (1-32).
            wait_time_sec: Visibility timeout in seconds for received messages.

        Returns:
            List of MessageQueueDict, possibly empty.
        """
        received = []
        for msg in self._client.receive_messages(
            max_messages=max_messages,
            visibility_timeout=wait_time_sec,
        ):
            self._pending[msg.pop_receipt] = msg.id
            body = _decode_message(msg.content)
            received.append(
                MessageQueueDict(body=body, ack_id=msg.pop_receipt, id=msg.id)
            )
        return received

    def delete_message(self, ack_id: str):
        message_id = self._pending.pop(ack_id, None)
        if message_id is None:
            raise ValueError(
                f'No pending message found for ack_id {ack_id!r}. '
                'It may have already been deleted or never received.'
            )
        self._client.delete_message(message_id, ack_id)

    def add_message(
        self, message_body: dict, topic_name_or_queue_url: str | None = None
    ) -> str:
        if topic_name_or_queue_url and topic_name_or_queue_url != self._queue_name:
            client = QueueClient(
                account_url=self._account_url,
                queue_name=topic_name_or_queue_url,
                credential=self._credential,
                message_encode_policy=None,
                message_decode_policy=None,
            )
        else:
            client = self._client
        result = client.send_message(json.dumps(message_body))
        return result.id
