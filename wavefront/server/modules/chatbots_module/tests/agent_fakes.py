"""Test doubles for agent-backed chat: a scripted model and an in-memory store."""

import uuid
from types import SimpleNamespace
from typing import Any, Optional

from flo_ai.llm.base_llm import BaseLLM
from flo_ai.tool import Tool


class ScriptedLLM(BaseLLM):
    """Replays a fixed list of responses and records every request."""

    def __init__(self, responses):
        self.model = 'scripted'
        self.temperature = 0
        self.kwargs = {}
        self.api_key = None
        self.responses = list(responses)
        self.requests = []

    async def generate(self, messages, functions=None, output_schema=None, **kwargs):
        self.requests.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def stream(self, *args, **kwargs):
        yield None

    def get_message_content(self, response):
        return response.get('text')

    async def get_function_call(self, response):
        return response.get('call')

    def format_tool_for_llm(self, tool):
        return {'name': tool.name}

    def format_tools_for_llm(self, tools):
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image):
        return ''

    async def format_document_in_message(self, document):
        return ''

    def format_tool_call_message(self, content, tool_calls):
        # A provider that is sent the call itself, so replay can be asserted.
        return {
            'role': 'assistant',
            'content': content,
            'call': (tool_calls[0].name, tool_calls[0].arguments),
        }


def text(content):
    return {'text': content}


def tool_call(name, call_id=None, **arguments):
    return {'call': {'name': name, 'arguments': arguments, 'id': call_id}}


def order_tool(lookups: Optional[list] = None, fail: bool = False) -> Tool:
    async def get_order_status(order_id: str) -> str:
        if lookups is not None:
            lookups.append(order_id)
        if fail:
            raise RuntimeError('order database is offline')
        return f'{order_id} shipped'

    return Tool(
        name='get_order_status',
        description='Look up an order',
        function=get_order_status,
        parameters={'order_id': {'type': 'string', 'description': 'Order id'}},
    )


class InMemoryChatStore:
    """Stands in for ChatSessionService and the message repository."""

    def __init__(self, fail_on_add: Optional[int] = None):
        self.rows: list = []
        self.deleted: list = []
        self._adds = 0
        self._fail_on_add = fail_on_add

    async def add_message(
        self,
        session_id,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self._adds += 1
        if self._fail_on_add is not None and self._adds == self._fail_on_add:
            raise RuntimeError('database is down')
        row = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            metadata_=metadata,
        )
        self.rows.append(row)
        return row

    async def get_history(self, session_id, limit: int = 50):
        return self.rows[-limit:]

    # The repository method AgentChatService uses to discard a declined turn.
    async def delete_all(self, **filters) -> bool:
        row_id = filters['id']
        self.deleted.append(row_id)
        self.rows = [row for row in self.rows if row.id != row_id]
        return True

    def shape(self) -> list:
        """(role, content, metadata) of every stored row, for assertions."""
        return [(row.role, row.content, row.metadata_) for row in self.rows]
