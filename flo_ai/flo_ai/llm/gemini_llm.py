import base64
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from .base_llm import BaseLLM
from flo_ai.models.chat_message import ImageMessageContent
from google import genai
from google.genai import types
from flo_ai.tool.base_tool import Tool
from flo_ai.telemetry.instrumentation import (
    trace_llm_call,
    trace_llm_stream,
    llm_metrics,
    add_span_attributes,
)
from flo_ai.telemetry import get_tracer
from opentelemetry import trace


class Gemini(BaseLLM):
    def __init__(
        self,
        model: str = 'gemini-2.5-flash',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: str = None,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        # Configure http_options for proxy or custom base_url
        http_options = {'base_url': base_url} if base_url else {}
        if base_url and self.api_key:
            # For custom base_url (proxy), set Authorization header explicitly
            http_options['headers'] = {'Authorization': f'Bearer {self.api_key}'}
            # Merge custom headers if provided (proxy scenario)
            if custom_headers:
                http_options['headers'].update(custom_headers)

        # Initialize client based on configuration
        if http_options:
            self.client = genai.Client(http_options=http_options)
        elif self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = genai.Client()

    @trace_llm_call(provider='gemini')
    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        # Convert messages to Gemini format
        contents = []
        system_prompt = ''

        for msg in messages:
            role = msg['role']
            message_content = msg['content']

            if role == 'system':
                system_prompt += f'{message_content}\n'
            else:
                contents.append(message_content)

        try:
            # Prepare generation config
            # Merge instance kwargs with method kwargs
            config_kwargs = {**self.kwargs, **kwargs}
            generation_config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=system_prompt,
                **config_kwargs,
            )

            # Add tools if functions are provided
            if functions:
                tools = types.Tool(function_declarations=functions)
                generation_config.tools = [tools]

            # Add structured output configuration if output_schema is provided
            if output_schema:
                generation_config.response_mime_type = 'application/json'
                generation_config.response_schema = output_schema

            # Make the API call (run in thread pool to avoid blocking event loop)
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
                config=generation_config,
            )

            # Record token usage if available
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0)
                completion_tokens = getattr(usage, 'candidates_token_count', 0)
                total_tokens = getattr(usage, 'total_token_count', 0)

                llm_metrics.record_tokens(
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    model=self.model,
                    provider='gemini',
                )

                # Add token info to current span
                tracer = get_tracer()
                if tracer:
                    current_span = trace.get_current_span()
                    add_span_attributes(
                        current_span,
                        {
                            'llm.tokens.prompt': prompt_tokens,
                            'llm.tokens.completion': completion_tokens,
                            'llm.tokens.total': total_tokens,
                        },
                    )

            # Check for function call in the response
            if (
                functions
                and response.candidates
                and response.candidates[0].content.parts
            ):
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'function_call') and part.function_call:
                    function_call = part.function_call
                    return {
                        'content': response.text,
                        'function_call': {
                            'name': function_call.name,
                            'arguments': function_call.args,
                        },
                    }

            # Return regular text response
            response_text = (
                response.text if hasattr(response, 'text') else str(response)
            )
            return {'content': response_text}

        except Exception as e:
            raise Exception(f'Error in Gemini API call: {str(e)}')

    @trace_llm_stream(provider='gemini')
    async def stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from Gemini as they are generated"""
        # Convert messages to Gemini format
        contents = []
        system_prompt = ''

        for msg in messages:
            role = msg['role']
            message_content = msg['content']

            if role == 'system':
                system_prompt += f'{message_content}\n'
            else:
                contents.append(message_content)

        # Prepare generation config
        # Merge instance kwargs with method kwargs
        config_kwargs = {**self.kwargs, **kwargs}
        generation_config = types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=system_prompt,
            **config_kwargs,
        )

        # Add tools if functions are provided
        if functions:
            tools = types.Tool(function_declarations=functions)
            generation_config.tools = [tools]

        # Get stream in thread to avoid blocking the initial call
        stream = await asyncio.to_thread(
            self.client.models.generate_content_stream,
            model=self.model,
            contents=contents,
            config=generation_config,
        )

        # Helper to get next chunk in thread pool
        def get_next_chunk():
            try:
                return next(stream)
            except StopIteration:
                return None

        # Iterate over synchronous stream without blocking event loop
        while True:
            chunk = await asyncio.to_thread(get_next_chunk)
            if chunk is None:
                break
            if hasattr(chunk, 'text') and chunk.text:
                yield {'content': chunk.text}

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        if isinstance(response, dict):
            return response.get('content', '')
        return str(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for Gemini's function declarations"""
        return {
            'name': tool.name,
            'description': tool.description,
            'parameters': {
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
        """Format tools for Gemini's function declarations"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> str:
        """Format a image in the message"""

        if image.base64:
            return types.Part.from_bytes(
                data=base64.b64decode(image.base64),
                mime_type=image.mime_type,
            )
        elif image.url:
            return types.Part.from_uri(
                file_uri=image.url,
                mime_type=image.mime_type,
            )
        raise NotImplementedError(
            f'Image formatting for Gemini LLM requires either url or base64 data. Received: url={image.url}, base64={bool(image.base64)}'
        )
