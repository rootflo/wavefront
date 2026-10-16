"""Chat Completions tool calling, shared by the OpenAI-protocol providers.

Uses the ``tools`` / ``tool_calls`` / ``role: tool`` protocol. The legacy
``functions`` / ``function_call`` / ``role: function`` one is rejected by newer
models (GPT-5.x on Azure among them).
"""

import json
from typing import Any, Dict, List, Optional

from flo_ai.tool.base_tool import Tool


def _as_tool(spec: Dict[str, Any]) -> Dict[str, Any]:
    """A tool definition, accepting the legacy bare function shape too."""
    if spec.get('type') == 'function' and 'function' in spec:
        return spec
    return {'type': 'function', 'function': spec}


class OpenAIToolCallingMixin:
    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        return {
            'type': 'function',
            'function': {
                'name': tool.name,
                'description': tool.description,
                'parameters': {
                    'type': 'object',
                    'properties': {
                        name: {
                            'type': info['type'],
                            'description': info['description'],
                            **(
                                {'items': info['items']}
                                if info.get('type') == 'array' and 'items' in info
                                else {}
                            ),
                        }
                        for name, info in tool.parameters.items()
                    },
                    'required': list(tool.parameters.keys()),
                },
            },
        }

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        return [self.format_tool_for_llm(tool) for tool in tools]

    @staticmethod
    def _tool_request_kwargs(
        functions: Optional[List[Dict[str, Any]]],
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """``tools``/``tool_choice`` request params; the schema forces its own tool."""
        if output_schema:
            name = output_schema.get('title', 'default')
            return {
                'tools': [
                    _as_tool(
                        {
                            'name': name,
                            'parameters': output_schema.get('schema', output_schema),
                        }
                    )
                ],
                'tool_choice': {'type': 'function', 'function': {'name': name}},
            }
        if functions:
            return {'tools': [_as_tool(spec) for spec in functions]}
        return {}

    @staticmethod
    def _to_tool_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """``messages`` with legacy ``role: function`` results rewritten.

        Those come from replaying the agent's history, which keeps tool
        results but not the assistant turn that requested them. A ``tool``
        message must answer a ``tool_calls`` entry, so each one gets a
        synthetic call (arguments unknown, sent as ``{}``) in front of it.
        """
        result: List[Dict[str, Any]] = []
        for index, msg in enumerate(messages):
            if msg.get('role') != 'function':
                result.append(msg)
                continue
            call_id = (
                msg.get('tool_call_id') or msg.get('tool_use_id') or f'call_{index}'
            )
            result.append(
                {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [
                        {
                            'id': call_id,
                            'type': 'function',
                            'function': {
                                'name': msg.get('name') or 'tool',
                                'arguments': '{}',
                            },
                        }
                    ],
                }
            )
            result.append(
                {
                    'role': 'tool',
                    'tool_call_id': call_id,
                    'content': msg.get('content') or '',
                }
            )
        return result

    async def get_function_call(self, response: Any) -> Optional[Dict[str, Any]]:
        if isinstance(response, dict):
            tool_calls = response.get('tool_calls')
        else:
            tool_calls = getattr(response, 'tool_calls', None)
        if isinstance(tool_calls, (list, tuple)) and tool_calls:
            # One call per turn: format_tool_call_message records only this
            # one, so the request never carries an unanswered call.
            call = tool_calls[0]
            if isinstance(call, dict):
                function, call_id = call['function'], call.get('id')
                name, arguments = function['name'], function['arguments']
            else:
                call_id = call.id
                name, arguments = call.function.name, call.function.arguments
            return {'name': name, 'arguments': arguments, 'id': call_id}
        return await super().get_function_call(response)  # type: ignore[misc]

    def format_tool_call_message(
        self, response: Any, function_call: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        call_id = function_call.get('id')
        if not call_id:
            return None
        arguments = function_call['arguments']
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        return {
            'role': 'assistant',
            'content': self.get_message_content(response) or None,  # type: ignore[attr-defined]
            'tool_calls': [
                {
                    'id': call_id,
                    'type': 'function',
                    'function': {'name': function_call['name'], 'arguments': arguments},
                }
            ],
        }

    def format_function_result_message(
        self, function_name: str, content: str, tool_use_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not tool_use_id:
            return super().format_function_result_message(  # type: ignore[misc]
                function_name, content, tool_use_id
            )
        return {'role': 'tool', 'tool_call_id': tool_use_id, 'content': content}
