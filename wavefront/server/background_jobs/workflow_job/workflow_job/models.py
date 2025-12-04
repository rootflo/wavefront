from flo_utils.streaming.event_message import BaseEventMessage
from dataclasses import dataclass


@dataclass
class WorkflowEventMessage(BaseEventMessage):
    body: dict
