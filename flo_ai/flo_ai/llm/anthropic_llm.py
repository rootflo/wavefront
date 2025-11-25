from typing import Dict, Any, List, Optional, AsyncIterator
from anthropic import AsyncAnthropic
import json

from flo_ai.models.chat_message import ImageMessageContent
from .base_llm import BaseLLM
from flo_ai.tool.base_tool import Tool
from flo_ai.telemetry.instrumentation import (
    trace_llm_call,
    trace_llm_stream,
    llm_metrics,
    add_span_attributes,
)
from flo_ai.telemetry import get_tracer
from opentelemetry import trace


class Anthropic(BaseLLM):
    def __init__(
        self,
        model: str = 'claude-3-5-sonnet-20240620',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: str = None,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        # Add custom headers if base_url is provided (proxy scenario)
        client_kwargs = {'api_key': self.api_key, 'base_url': base_url}
        if base_url and custom_headers:
            client_kwargs['default_headers'] = custom_headers

        self.client = AsyncAnthropic(**client_kwargs)

    @trace_llm_call(provider='anthropic')
    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        # Convert messages to Claude format
        system_message = next(
            (msg['content'] for msg in messages if msg['role'] == 'system'), None
        )

        # If output schema is provided, append it to system message
        if output_schema and system_message:
            system_message = f'{system_message}\n\nProvide output in the following JSON schema:\n{json.dumps(output_schema, indent=2)}\n\nResponse:'
        elif output_schema:
            system_message = f'Provide output in the following JSON schema:\n{json.dumps(output_schema, indent=2)}\n\nResponse:'

        conversation = []
        for msg in messages:
            if msg['role'] != 'system':
                # Handle function/tool result messages specially for Claude
                if msg['role'] == 'function':
                    # Claude expects tool results in a specific format
                    # If this is a tool result, format it as a user message with tool_result content
                    tool_use_id = msg.get('tool_use_id', 'unknown')
                    conversation.append(
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'tool_result',
                                    'tool_use_id': tool_use_id,
                                    'content': msg['content'],
                                }
                            ],
                        }
                    )
                else:
                    conversation.append(
                        {
                            'role': 'assistant'
                            if msg['role'] == 'assistant'
                            else 'user',
                            'content': msg['content'],
                        }
                    )

        try:
            anthropic_kwargs = {
                'model': self.model,
                'messages': conversation,
                'temperature': self.temperature,
                'max_tokens': self.kwargs.get('max_tokens', 1024),
                **self.kwargs,
                **kwargs,
            }

            if system_message:
                anthropic_kwargs['system'] = system_message

            if functions:
                anthropic_kwargs['tools'] = functions

            response = await self.client.messages.create(**anthropic_kwargs)

            # Record token usage if available
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                llm_metrics.record_tokens(
                    total_tokens=usage.input_tokens + usage.output_tokens,
                    prompt_tokens=usage.input_tokens,
                    completion_tokens=usage.output_tokens,
                    model=self.model,
                    provider='anthropic',
                )

                # Add token info to current span
                tracer = get_tracer()
                if tracer:
                    current_span = trace.get_current_span()
                    add_span_attributes(
                        current_span,
                        {
                            'llm.tokens.prompt': usage.input_tokens,
                            'llm.tokens.completion': usage.output_tokens,
                            'llm.tokens.total': usage.input_tokens
                            + usage.output_tokens,
                        },
                    )

            # Extract text content from TextBlock objects
            text_content = ''
            for content_block in response.content:
                if content_block.type == 'text':
                    text_content = content_block.text
                    break

            # Check if there's a tool use in the response
            for content_block in response.content:
                if content_block.type == 'tool_use':
                    return {
                        'content': text_content,
                        'raw_content': response.content,  # Store raw content for Claude's tool flow
                        'function_call': {
                            'name': content_block.name,
                            'arguments': json.dumps(content_block.input),
                            'id': content_block.id,  # Include the tool_use_id for Claude
                        },
                    }

            # Handle regular text response
            return {'content': text_content}

        except Exception as e:
            raise Exception(f'Error in Claude API call: {str(e)}')

    @trace_llm_stream(provider='anthropic')
    async def stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from the LLM as they are generated"""
        # Convert messages to Claude format
        system_message = next(
            (msg['content'] for msg in messages if msg['role'] == 'system'), None
        )

        conversation = []
        for msg in messages:
            if msg['role'] != 'system':
                conversation.append(
                    {
                        'role': 'assistant' if msg['role'] == 'assistant' else 'user',
                        'content': msg['content'],
                    }
                )

        anthropic_kwargs = {
            'model': self.model,
            'messages': conversation,
            'temperature': self.temperature,
            'max_tokens': self.kwargs.get('max_tokens', 1024),
            **self.kwargs,
            **kwargs,
        }

        if system_message:
            anthropic_kwargs['system'] = system_message

        if functions:
            anthropic_kwargs['tools'] = functions
        # Use Anthropic SDK streaming API and yield text deltas
        async with self.client.messages.stream(**anthropic_kwargs) as stream:
            async for event in stream:
                if (
                    getattr(event, 'type', None) == 'content_block_delta'
                    and hasattr(event, 'delta')
                    and getattr(event.delta, 'type', None) == 'text_delta'
                    and hasattr(event.delta, 'text')
                ):
                    yield {'content': event.delta.text}

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        if isinstance(response, dict):
            return response.get('content', '')
        return str(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for Claude's API"""
        return {
            'type': 'custom',
            'name': tool.name,
            'description': tool.description,
            'input_schema': {
                'type': 'object',
                'properties': {
                    name: {
                        'type': info.get('type', 'string'),
                        'description': info.get('description', ''),
                        **(
                            {'items': info['items']}
                            if info.get('type') == 'array' and 'items' in info
                            else {}
                        ),
                    }
                    for name, info in tool.parameters.items()
                },
                'required': [
                    name
                    for name, info in tool.parameters.items()
                    if info.get('required', True)
                ],
            },
        }

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        """Format tools for Claude's API"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> str:
        """Format a image in the message"""
        raise NotImplementedError('Not implemented image for LLM Anthropic')

    def get_assistant_message_for_tool_call(
        self, response: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Get the assistant message content for tool calls.
        For Claude, this returns the raw_content which includes tool_use blocks.
        For other LLMs, returns None to use default text content.
        """
        if isinstance(response, dict) and 'raw_content' in response:
            return response['raw_content']
        return None

    def get_tool_use_id(self, function_call: Dict[str, Any]) -> Optional[str]:
        """
        Extract tool_use_id from function call if available.
        Returns the ID for Claude's tool_use tracking, None for other LLMs.
        """
        return function_call.get('id')

    def format_function_result_message(
        self, function_name: str, content: str, tool_use_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format a function result message for the LLM.
        For Claude, includes tool_use_id in the message.
        """
        message = {
            'role': 'function',
            'name': function_name,
            'content': content,
        }
        if tool_use_id:
            message['tool_use_id'] = tool_use_id
        return message
