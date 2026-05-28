from typing import Dict, Any, List, AsyncIterator, Optional

from openai import AsyncAzureOpenAI

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


class AzureOpenAI(BaseLLM):
    def __init__(
        self,
        model: str,
        api_key: Optional[str],
        azure_endpoint: str,
        api_version: str = '2024-12-01-preview',
        temperature: float = 0.7,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """
        Azure OpenAI LLM implementation using the AsyncAzureOpenAI client.

        Args:
            model: Azure deployment name (passed as `model` to chat.completions.create)
            api_key: Azure OpenAI API key
            azure_endpoint: Azure endpoint URL, e.g. https://<resource>.cognitiveservices.azure.com/
            api_version: Azure OpenAI API version
            temperature: Sampling temperature
            custom_headers: Optional additional headers to send with each request
            **kwargs: Extra parameters forwarded to the SDK client / calls

        PDFs are sent to the underlying deployment as rasterized page images
        via the Chat Completions multimodal format. The deployment must be
        vision-capable (gpt-4o, gpt-4.1, gpt-5, etc.); text-only deployments
        will error on the first document call.
        """
        super().__init__(
            model=model,
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            default_headers=custom_headers,
            **kwargs,
        )
        self.model = model
        self.kwargs = kwargs

    @trace_llm_call(provider='azureopenai')
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        # Handle structured output vs tool calling
        if output_schema:
            kwargs['response_format'] = {'type': 'json_object'}
            kwargs['functions'] = [
                {
                    'name': output_schema.get('title', 'default'),
                    'parameters': output_schema.get('schema', output_schema),
                }
            ]
            kwargs['function_call'] = {'name': output_schema.get('title', 'default')}

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
            kwargs['functions'] = functions

        azure_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            **self.kwargs,
            **kwargs,
        }

        response = await self.client.chat.completions.create(**azure_kwargs)
        message = response.choices[0].message

        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            llm_metrics.record_tokens(
                total_tokens=usage.total_tokens,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                model=self.model,
                provider='azureopenai',
            )

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

        return message

    @trace_llm_stream(provider='azureopenai')
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from Azure OpenAI Chat Completions API."""
        azure_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'stream': True,
            **self.kwargs,
            **kwargs,
        }

        if functions:
            azure_kwargs['functions'] = functions

        response = await self.client.chat.completions.create(**azure_kwargs)
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
        if isinstance(response, str):
            return response
        if hasattr(response, 'content') and response.content is not None:
            return str(response.content)
        return ''

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for Azure OpenAI's API (OpenAI-compatible)."""
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
        """Format tools for Azure OpenAI's API (OpenAI-compatible)."""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> list[dict]:
        """
        Format an image in the message for Azure OpenAI.

        Azure vision models expect the OpenAI-style `"image_url"` block, for example:
        {
            "type": "image_url",
            "image_url": { "url": "data:image/png;base64,..." }
        }
        """
        import base64

        # Remote URL
        if image.url:
            return [
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': image.url,
                    },
                }
            ]

        # Raw base64 string or bytes – construct a data URL
        if image.base64 or image.bytes:
            if not image.mime_type:
                raise ValueError(
                    'Image mime type is required for Azure OpenAI image messages'
                )

            if image.base64:
                b64 = image.base64
            else:
                b64 = base64.b64encode(image.bytes or b'').decode('utf-8')

            data_url = f'data:{image.mime_type};base64,{b64}'

            return [
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': data_url,
                    },
                }
            ]

        raise NotImplementedError(
            f'Image formatting for AzureOpenAI LLM requires either url, base64 data, or bytes. '
            f'Received: url={image.url}, base64={bool(image.base64)}, bytes={bool(image.bytes)}'
        )
