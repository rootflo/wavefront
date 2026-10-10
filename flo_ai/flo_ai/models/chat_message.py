from typing import List, Literal, Optional, Dict, Any
from dataclasses import dataclass, field


class MessageType:
    USER = 'user'
    ASSISTANT = 'assistant'
    FUNCTION = 'function'
    SYSTEM = 'system'


@dataclass
class MediaMessageContent:
    type: Optional[Literal['text', 'image', 'document']] = None
    url: Optional[str] = None
    base64: Optional[str] = None
    mime_type: Optional[str] = None
    # Original name of the uploaded file, carried through for traceability.
    # Not sent to the LLM — provider payloads ignore it.
    file_name: Optional[str] = None


@dataclass
class ImageMessageContent(MediaMessageContent):
    url: Optional[str] = None
    base64: Optional[str] = None
    mime_type: Optional[str] = None
    bytes: Optional[bytes] = None

    def __post_init__(self):
        self.type = 'image'
        self._formatted_cache: Dict[str, Any] = {}


@dataclass
class DocumentMessageContent(MediaMessageContent):
    url: Optional[str] = None
    base64: Optional[str] = None
    bytes: Optional[bytes] = None
    mime_type: Optional[str] = None

    def __post_init__(self):
        self.type = 'document'
        # Cache of provider-formatted payloads keyed by LLM class name.
        # Avoids re-running PDF rasterization / text extraction across
        # multiple agent nodes or retry attempts.
        self._formatted_cache: Dict[str, Any] = {}


@dataclass
class TextMessageContent:
    text: str
    type: str = 'text'


@dataclass
class BaseMessage:
    content: str | ImageMessageContent | DocumentMessageContent | TextMessageContent
    role: Optional[Literal['system', 'user', 'assistant', 'function']] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SystemMessage(BaseMessage):
    content: str
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.role = 'system'


@dataclass
class UserMessage(BaseMessage):
    content: str | ImageMessageContent | DocumentMessageContent | TextMessageContent
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.role = 'user'


@dataclass
class ToolCall:
    """A tool the model asked to run."""

    name: str
    arguments: Dict[str, Any]
    # The provider's id for the call, where it issues one. It ties the call to
    # its result (FunctionMessage.tool_call_id).
    id: Optional[str] = None


@dataclass
class AssistantMessage(BaseMessage):
    content: str
    metadata: Optional[Dict[str, Any]] = None
    role: Optional[str] = None
    # Set when this turn of the model was a request to run tools. `content`
    # then holds whatever text came with the request, possibly none.
    tool_calls: Optional[List[ToolCall]] = None

    def __post_init__(self):
        if self.role is None:
            self.role = MessageType.ASSISTANT


@dataclass
class FunctionMessage(BaseMessage):
    """Message representing a function/tool call result.

    According to OpenAI's API, function results should use:
    {
        "role": "function",
        "name": "<function-name>",
        "content": "<result>"
    }
    """

    content: str  # Override parent's content (must come before fields with defaults)
    name: str = field(
        kw_only=True
    )  # Function/tool name that was called (keyword-only to allow it after defaults)
    # The id of the ToolCall this answers, where the provider issued one.
    tool_call_id: Optional[str] = field(default=None, kw_only=True)

    def __post_init__(self):
        self.role = MessageType.FUNCTION
