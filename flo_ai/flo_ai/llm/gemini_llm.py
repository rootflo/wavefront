import base64
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from .base_llm import BaseLLM
from flo_ai.utils.logger import logger
from flo_ai.models.chat_message import DocumentMessageContent, ImageMessageContent
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
    provider_name = 'gemini'

    def __init__(
        self,
        model: str = 'gemini-2.5-flash',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        # Configure http_options for proxy or custom base_url
        http_options: types.HttpOptionsDict = {'base_url': base_url} if base_url else {}
        # The key travels as `x-goog-api-key`, which the SDK sets from the key
        # passed below. It used to also go out as `Authorization: Bearer`, but
        # an Authorization header makes Google's frontend look for an OAuth2
        # principal instead of accepting the key, and reject the request - so a
        # proxy in front has to authenticate on the SDK's own header.
        # `custom_headers` is unrelated: it identifies the caller to the proxy
        # (X-Rootflo-Key), so it does not depend on an api_key having been
        # passed - the SDK resolves that from the environment on its own, and
        # gating on the argument would drop the caller's identity from a
        # request that goes on to authenticate to Google perfectly well.
        if base_url and custom_headers:
            http_options['headers'] = dict(custom_headers)

        # Initialize client based on configuration
        if http_options:
            # The SDK refuses to construct without a key of some kind, so a
            # base_url configuration has to pass one here too - otherwise it
            # raises `Missing key inputs argument!` unless the environment
            # happens to carry one.
            self.client = genai.Client(api_key=self.api_key, http_options=http_options)
        elif self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = genai.Client()

    # The config layer uses OpenAI's name for the token limit.
    _CONFIG_ALIASES = {'max_tokens': 'max_output_tokens'}

    def _generation_config_kwargs(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Map generation params onto GenerateContentConfig's field names.

        GenerateContentConfig rejects unknown fields, so an unmapped param
        would fail the request rather than be ignored.

        Args:
            call_kwargs: Per-call params, which override the instance's

        Returns:
            Params accepted by types.GenerateContentConfig
        """
        config_kwargs: Dict[str, Any] = {}
        for key, value in {**self.kwargs, **call_kwargs}.items():
            field = self._CONFIG_ALIASES.get(key, key)
            if field in types.GenerateContentConfig.model_fields:
                config_kwargs[field] = value
            else:
                logger.warning(
                    f'Ignoring generation param not supported by Gemini: {key}'
                )
        return config_kwargs

    def _generation_config(
        self, system_prompt: str, call_kwargs: Dict[str, Any]
    ) -> 'types.GenerateContentConfig':
        """Build the request config, resolving what the caller may also have set.

        `temperature` and `system_instruction` are both ordinary
        GenerateContentConfig fields, so either can arrive in the params as well
        as from the arguments here - and passing one twice is a
        duplicate-keyword TypeError. Building the whole mapping and splatting it
        once keeps every field in the config single-valued by construction.

        Args:
            system_prompt: The system text collected from the messages
            call_kwargs: Per-call params, which override the instance's

        Returns:
            The config to send with the request
        """
        config_kwargs = self._generation_config_kwargs(call_kwargs)
        config_kwargs.setdefault('temperature', self.temperature)
        # The messages carry the agent's actual system prompt, so it outranks
        # one set as a generation param; with no system messages, a configured
        # instruction is the only one there is.
        if system_prompt or 'system_instruction' not in config_kwargs:
            config_kwargs['system_instruction'] = system_prompt
        return types.GenerateContentConfig(**config_kwargs)

    @trace_llm_call(provider='gemini')
    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[types.FunctionDeclaration]] = None,
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
            # Prepare generation config, merging instance and method kwargs
            generation_config = self._generation_config(system_prompt, kwargs)

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
        functions: Optional[List[types.FunctionDeclaration]] = None,
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

        # Prepare generation config, merging instance and method kwargs
        generation_config = self._generation_config(system_prompt, kwargs)

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

    def get_message_content(self, response: Dict[str, Any]) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            content = response.get('content')
            return str(content) if content is not None else ''

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

    def format_image_in_message(self, image: ImageMessageContent) -> types.Part:
        """Format a image in the message"""

        if image.base64:
            if image.mime_type is None:
                raise ValueError('Image mime type is required')

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

    async def format_document_in_message(
        self, document: DocumentMessageContent
    ) -> types.Part:
        """Return a Gemini native Part for this document.

        Gemini accepts PDFs (and many other document formats) as `inline_data`
        Parts, so there is no need to extract or rasterize locally.
        """
        cache_key = self.__class__.__name__
        cache = getattr(document, '_formatted_cache', None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]

        mime = document.mime_type or 'application/pdf'
        if document.bytes:
            part = types.Part.from_bytes(data=document.bytes, mime_type=mime)
        elif document.base64:
            part = types.Part.from_bytes(
                data=base64.b64decode(document.base64), mime_type=mime
            )
        elif document.url:
            part = types.Part.from_uri(file_uri=document.url, mime_type=mime)
        else:
            raise ValueError('DocumentMessageContent has no bytes, base64, or url')

        if isinstance(cache, dict):
            cache[cache_key] = part
        return part
