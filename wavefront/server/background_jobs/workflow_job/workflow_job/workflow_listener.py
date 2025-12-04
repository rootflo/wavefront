from flo_utils.streaming.stream_listner import StreamListener
from flo_cloud._types import MessageQueueDict
from flo_utils.streaming.event_message import BaseEventMessage
from typing import List
from .models import WorkflowEventMessage


class WorkflowListener(StreamListener):
    def get_event_messages(
        self, messages: List[MessageQueueDict]
    ) -> List[BaseEventMessage]:
        return [self.__make_event_message(msg) for msg in messages]

    def __make_event_message(self, message: MessageQueueDict) -> WorkflowEventMessage:
        return WorkflowEventMessage(
            id=message.id,
            ack_id=message.ack_id,
            body=message.body,
        )
