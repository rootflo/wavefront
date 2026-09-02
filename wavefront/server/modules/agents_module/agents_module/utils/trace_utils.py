"""
Serialize flo-ai execution memory (Arium's per-node MessageMemory, or a
single agent's conversation_history) into the JSON-safe `trace` recorded in
an execution's history.json — one entry per node/turn, in execution order,
so an eval agent can see which node/agent produced which output.

Media content (images/documents) is recorded as a reference (mime type +
storage url) only — never the raw base64/bytes payload.
"""

from typing import Any, Dict, List

from flo_ai import (
    BaseMessage,
    TextMessageContent,
    ImageMessageContent,
    DocumentMessageContent,
)
from flo_ai.arium import MessageMemoryItem


def _serialize_content(content: Any) -> Any:
    if isinstance(content, TextMessageContent):
        return content.text
    if isinstance(content, (ImageMessageContent, DocumentMessageContent)):
        return {
            'type': content.type,
            'mime_type': content.mime_type,
            'reference': content.url,
            'file_name': content.file_name,
        }
    return content


def _serialize_message(message: BaseMessage) -> Dict[str, Any]:
    return {
        'role': getattr(message, 'role', None),
        'name': getattr(message, 'name', None),
        'content': _serialize_content(getattr(message, 'content', message)),
        'metadata': getattr(message, 'metadata', None) or {},
    }


def serialize_memory_trace(
    memory_items: List[MessageMemoryItem],
) -> List[Dict[str, Any]]:
    """Serialize an Arium workflow's full MessageMemory (every node's output,
    plus the initial 'input' entries) in execution order."""
    return [
        {
            'node': item.node,
            'occurrence': item.occurrence,
            **_serialize_message(item.result),
        }
        for item in memory_items
    ]


def serialize_conversation_trace(
    agent_node: str, conversation: List[BaseMessage]
) -> List[Dict[str, Any]]:
    """Serialize a single agent's full conversation_history into the same
    trace shape as serialize_memory_trace. Messages the agent produced
    (assistant/function replies) are tagged with `agent_node`; messages it
    received (system/user) are tagged 'input', mirroring Arium's
    producer/input distinction.
    """
    trace = []
    for occurrence, message in enumerate(conversation, start=1):
        entry = _serialize_message(message)
        node = 'input' if entry['role'] in ('system', 'user') else agent_node
        trace.append({'node': node, 'occurrence': occurrence, **entry})
    return trace
