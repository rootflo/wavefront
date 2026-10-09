from dataclasses import dataclass


@dataclass
class BaseEventMessage:
    id: str
    ack_id: str
    body: dict
