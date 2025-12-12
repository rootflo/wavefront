from flo_utils.streaming.event_message import BaseEventMessage
from dataclasses import dataclass
from typing import Optional


@dataclass
class RagEventMessage(BaseEventMessage):
    """Event message for gold-related events."""

    bucket_name: str
    bucket_key: str
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None
    parse_type: Optional[str] = None
    file_type: Optional[str] = None
