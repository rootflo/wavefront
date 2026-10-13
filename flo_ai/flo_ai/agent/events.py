"""Events an agent reports while it runs, one per message it adds to its conversation."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Union

from flo_ai.models.chat_message import BaseMessage


class AgentEventType:
    # The model asked for a tool. `message` is an AssistantMessage with tool_calls.
    TOOL_CALL = 'tool_call'
    # A tool returned, or failed. `message` is a FunctionMessage.
    TOOL_RESULT = 'tool_result'
    # The model replied with text. `is_final` tells the answer from reasoning
    # the agent was asked to continue from.
    MESSAGE = 'message'
    # Text the agent put into its own conversation: a request to keep going,
    # or the analysis of an error before a retry.
    NOTICE = 'notice'


@dataclass
class AgentEvent:
    """One message the agent added to its conversation, as it was added.

    Taken together and in order, the events of a run are everything the run
    appended to ``conversation_history`` apart from the caller's inputs and the
    system message. Storing each ``message`` therefore stores the turn, and
    passing the stored messages back as inputs later replays it.
    """

    type: str
    agent: str
    message: BaseMessage
    is_final: bool = False


AgentEventCallback = Callable[[AgentEvent], Union[None, Awaitable[Any]]]
