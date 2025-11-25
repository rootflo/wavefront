import base64
from typing import Dict, Any, List, AsyncIterator, Optional
from openai import AsyncOpenAI
from .base_llm import BaseLLM
from flo_ai.models.chat_message import ImageMessageContent
from flo_ai.tool.base_tool import Tool
from flo_ai.telemetry.instrumentation import (
    trace_llm_call,
    trace_llm_stream,
    llm_metrics,
    add_span_attributes,
)
from flo_ai.telemetry import get_tracer
from opentelemetry import trace


class OpenAI(BaseLLM):
    def __init__(
        self,
        model='gpt-4o-mini',
        api_key: str = None,
        temperature: float = 0.7,
        base_url: str = None,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        super().__init__(
            model=model, api_key=api_key, temperature=temperature, **kwargs
        )
        # Add custom headers if base_url is provided (proxy scenario)
        client_kwargs = {'api_key': api_key, 'base_url': base_url}
        if base_url and custom_headers:
            client_kwargs['default_headers'] = custom_headers

        self.client = AsyncOpenAI(**client_kwargs)
        self.model = model
        self.kwargs = kwargs

    @trace_llm_call(provider='openai')
    async def generate(
        self,
        messages: list[dict],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: dict = None,
        **kwargs,
    ) -> Any:
        # Handle structured output vs tool calling
        # Priority: output_schema takes precedence over functions for structured output
        if output_schema:
            # Convert output_schema to OpenAI format for structured output
            kwargs['response_format'] = {'type': 'json_object'}
            kwargs['functions'] = [
                {
                    'name': output_schema.get('title', 'default'),
                    'parameters': output_schema.get('schema', output_schema),
                }
            ]
            kwargs['function_call'] = {'name': output_schema.get('title', 'default')}

            # Add JSON format instruction to the system prompt
            if messages and messages[0]['role'] == 'system':
                messages[0]['content'] = (
                    messages[0]['content']
                    + '\n\nPlease provide your response in JSON format according to the specified schema.'
                )
            else:
                messages.insert(
                    0,
                    {
                        'role': 'system',
                        'content': 'Please provide your response in JSON format according to the specified schema.',
                    },
                )
        elif functions:
            # Use functions for tool calling when output_schema is not provided
            kwargs['functions'] = functions

        # Prepare OpenAI API parameters
        openai_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            **self.kwargs,
            **kwargs,
        }

        # Make the API call
        response = await self.client.chat.completions.create(**openai_kwargs)
        message = response.choices[0].message

        # Record token usage if available
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            llm_metrics.record_tokens(
                total_tokens=usage.total_tokens,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                model=self.model,
                provider='openai',
            )

            # Add token info to current span
            tracer = get_tracer()
            if tracer:
                current_span = trace.get_current_span()
                add_span_attributes(
                    current_span,
                    {
                        'llm.tokens.prompt': usage.prompt_tokens,
                        'llm.tokens.completion': usage.completion_tokens,
                        'llm.tokens.total': usage.total_tokens,
                    },
                )

        # Return the full message object instead of just the content
        return message

    @trace_llm_stream(provider='openai')
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from OpenAI Chat Completions API."""
        # Prepare OpenAI API parameters
        openai_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'stream': True,
            **self.kwargs,
            **kwargs,
        }

        if functions:
            openai_kwargs['functions'] = functions

        # Stream the API call and yield content deltas
        response = await self.client.chat.completions.create(**openai_kwargs)
        async for chunk in response:
            choices = getattr(chunk, 'choices', []) or []
            for choice in choices:
                delta = getattr(choice, 'delta', None)
                if delta is None:
                    continue
                content = getattr(delta, 'content', None)
                if content:
                    yield {'content': content}

    def get_message_content(self, response: Dict[str, Any]) -> str:
        # Handle both string responses and message objects
        if isinstance(response, str):
            return response
        # Otherwise return content if available
        return response.content if hasattr(response, 'content') else str(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for OpenAI's API"""
        return {
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
        }

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        """Format tools for OpenAI's API"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> dict:
        """Format a image in the message"""
        if image.url:
            return {
                'type': 'input_image',
                'image': {
                    'url': image.url,
                    'mime_type': image.mime_type,
                },
            }
        elif image.base64:
            image_bytes = base64.b64decode(image.base64)
        else:
            raise NotImplementedError(
                f'Image formatting for OpenAI LLM requires either url or base64 data. Received: url={image.url}, base64={bool(image.base64)}'
            )
        image_64 = base64.b64encode(image_bytes).decode('utf-8')

        return {
            'type': 'input_image',
            'image': {
                'data': image_64,
                'mime_type': image.mime_type,
            },
        }
