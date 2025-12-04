from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class QueueMessage:
    message_id: str
    message_reciept_id: str
    bucket_name: str
    key: str
    worker_id: Optional[str] = None
    parse_type: Optional[str] = None
    image_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None
    file_type: Optional[str] = None


@dataclass
class EventMessage:
    id: str

    ack_id: str

    # should be a json set from
    body: dict

    # parse type, either lambda or buckets
    parse_type: str

    # for bucket cases
    bucket_name: Optional[str] = None

    # for file in buckets
    bucket_key: Optional[str] = None

    # kb_id for knowledge base
    kb_id: Optional[str] = None

    # document_id for knowledge base
    doc_id: Optional[str] = None
