from typing import Dict, Any, List, Optional, AsyncIterator
from anthropic import AsyncAnthropic
import json
import re

import base64 as _base64

from flo_ai.models.agent_error import ModelRefusedError
from flo_ai.models.chat_message import DocumentMessageContent, ImageMessageContent
from .base_llm import BaseLLM, split_client_kwargs
from flo_ai.tool.base_tool import Tool
from flo_ai.telemetry.instrumentation import (
    trace_llm_call,
    trace_llm_stream,
    llm_metrics,
    add_span_attributes,
)
from flo_ai.telemetry import get_tracer
from opentelemetry import trace


_SAMPLING_PARAMS = ('temperature', 'top_p', 'top_k')

# Model ids that reject sampling params: claude-opus-4-7, claude-opus-4-8,
# claude-opus-5 and later, claude-sonnet-5 and later, and the Fable and Mythos
# lines. Searched, not matched, so provider prefixes (`anthropic.claude-...`)
# are covered.
_NO_SAMPLING_PARAMS = re.compile(
    r'claude-(?:opus-(?:4-[78]|[5-9])|sonnet-[5-9]|fable|mythos)'
)

_DEFAULT_MAX_TOKENS_WITH_THINKING = 16000

# Model ids that reject a request ending on an assistant message (prefill):
# claude-opus-4-6 and later, claude-sonnet-4-6 and later, Fable and Mythos.
_NO_PREFILL = re.compile(
    r'claude-(?:opus-(?:4-[6-8]|[5-9])|sonnet-(?:4-6|[5-9])|fable|mythos)'
)

# The agent loop runs one tool per model turn. Claude otherwise may ask for
# several at once, and every tool_use it sends must be answered.
_ONE_TOOL_CALL_PER_TURN = {'type': 'auto', 'disable_parallel_tool_use': True}


class Anthropic(BaseLLM):
    provider_name = 'anthropic'

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = 'claude-3-5-sonnet-20240620',
        temperature: float = 0.7,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        client_kwargs, request_kwargs = split_client_kwargs(
            AsyncAnthropic, kwargs, reserved=('default_headers',)
        )

        super().__init__(
            model=model,
            api_key=api_key,
            temperature=temperature,
            **request_kwargs,
        )

        self.client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=base_url,
            default_headers=custom_headers,
            **client_kwargs,
        )

    def _takes_sampling_params(self) -> bool:
        """Whether this model accepts temperature, top_p and top_k.

        Claude Opus 4.7 and every Opus, Sonnet, Fable and Mythos model since
        answer a request that carries any of them with a 400.
        """
        return not _NO_SAMPLING_PARAMS.search(self.model or '')

    def _end_on_user_turn(
        self, conversation: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Make a conversation that ends on an assistant turn end on a user one.

        An agent in a workflow is handed the outputs of the agents before it,
        and those are assistant messages. Models that reject prefill refuse a
        request ending that way; what they are being asked is to respond to
        that last message, so it is sent as the user's.
        """
        if (
            not conversation
            or conversation[-1]['role'] != 'assistant'
            or not _NO_PREFILL.search(self.model or '')
        ):
            return conversation
        return [*conversation[:-1], {**conversation[-1], 'role': 'user'}]

    def _request_params(
        self, conversation: List[Dict[str, Any]], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """The params for messages.create/stream, apart from system and tools"""
        params: Dict[str, Any] = {
            'model': self.model,
            'messages': conversation,
            'temperature': self.temperature,
            'max_tokens': 1024,
            **self.kwargs,
            **overrides,
        }

        if not self._takes_sampling_params():
            for name in _SAMPLING_PARAMS:
                params.pop(name, None)
            # Thinking is on for these models and counts toward max_tokens, so
            # a limit sized for a reply alone cuts the reply off.
            if 'max_tokens' not in self.kwargs and 'max_tokens' not in overrides:
                params['max_tokens'] = _DEFAULT_MAX_TOKENS_WITH_THINKING

        return params

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
            anthropic_kwargs = self._request_params(
                self._end_on_user_turn(conversation), kwargs
            )

            if system_message:
                anthropic_kwargs['system'] = system_message

            if functions:
                anthropic_kwargs['tools'] = functions
                anthropic_kwargs.setdefault('tool_choice', _ONE_TOOL_CALL_PER_TURN)

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

            # A refusal comes back as a normal response with no text. Left
            # unreported it would read as an empty reply from the model.
            if getattr(response, 'stop_reason', None) == 'refusal':
                details = getattr(response, 'stop_details', None)
                category = getattr(details, 'category', None)
                explanation = getattr(details, 'explanation', None)
                raise ModelRefusedError(
                    f'{self.model} declined the request'
                    + (f' (category: {category})' if category else '')
                    + (f': {explanation}' if explanation else ''),
                    category=category,
                    explanation=explanation,
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
                        # Raw content for Claude's tool flow. Only this call
                        # is run and answered, so any further tool_use block
                        # is left out: sent back unanswered, it would make the
                        # next request invalid.
                        'raw_content': [
                            block
                            for block in response.content
                            if block.type != 'tool_use' or block is content_block
                        ],
                        'function_call': {
                            'name': content_block.name,
                            'arguments': json.dumps(content_block.input),
                            'id': content_block.id,  # Include the tool_use_id for Claude
                        },
                    }

            # Handle regular text response
            return {'content': text_content}

        except ModelRefusedError:
            raise
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

        anthropic_kwargs = self._request_params(
            self._end_on_user_turn(conversation), kwargs
        )

        if system_message:
            anthropic_kwargs['system'] = system_message

        if functions:
            anthropic_kwargs['tools'] = functions
            anthropic_kwargs.setdefault('tool_choice', _ONE_TOOL_CALL_PER_TURN)
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

    async def _format_native_document(
        self, document: DocumentMessageContent
    ) -> List[Dict[str, Any]]:
        """Return a native Claude document content block.

        Claude accepts PDFs directly as base64-encoded document blocks, so we
        skip any local PDF parsing entirely. Caching is handled by the base.
        """
        mime = document.mime_type or 'application/pdf'
        if document.base64:
            b64 = document.base64
        elif document.bytes:
            b64 = _base64.b64encode(document.bytes).decode('utf-8')
        elif document.url:
            return [
                {
                    'type': 'document',
                    'source': {'type': 'url', 'url': document.url},
                }
            ]
        else:
            raise ValueError('DocumentMessageContent has no bytes, base64, or url')

        return [
            {
                'type': 'document',
                'source': {
                    'type': 'base64',
                    'media_type': mime,
                    'data': b64,
                },
            }
        ]

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

    def format_tool_call_message(
        self, content: str, tool_calls: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """An assistant message with a tool_use block per call"""
        blocks: List[Dict[str, Any]] = []
        if content:
            blocks.append({'type': 'text', 'text': content})
        for call in tool_calls:
            blocks.append(
                {
                    'type': 'tool_use',
                    'id': call.id or 'unknown',
                    'name': call.name,
                    'input': call.arguments,
                }
            )
        return {'role': 'assistant', 'content': blocks}

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
