from typing import Dict, Any, List, Optional, AsyncIterator
import aiohttp
import json

from flo_ai.models.chat_message import ImageMessageContent
from .base_llm import BaseLLM
from flo_ai.tool.base_tool import Tool
from flo_ai.telemetry.instrumentation import trace_llm_call, trace_llm_stream


class OllamaLLM(BaseLLM):
    def __init__(
        self,
        model: str = 'llama2',
        api_key: str = None,
        temperature: float = 0.7,
        base_url: str = 'http://localhost:11434',
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        self.base_url = base_url.rstrip('/')

    @trace_llm_call(provider='ollama')
    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Convert messages to Ollama format
        prompt = ''
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == 'system':
                prompt += f'System: {content}\n'
            elif role == 'user':
                prompt += f'User: {content}\n'
            elif role == 'assistant':
                prompt += f'Assistant: {content}\n'

        # Add output schema instruction if provided
        if output_schema:
            prompt += f'\nPlease provide your response in JSON format according to this schema:\n{json.dumps(output_schema, indent=2)}\n'

        # Prepare request payload
        payload = {
            'model': self.model,
            'prompt': prompt,
            'temperature': self.temperature,
            'stream': False,
            **self.kwargs,
        }

        # Add function information if provided
        if functions:
            payload['functions'] = functions

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/api/generate', json=payload
            ) as response:
                if response.status != 200:
                    raise Exception(f'Ollama API error: {await response.text()}')

                result = await response.json()
                return {
                    'content': result.get('response', ''),
                    'function_call': result.get('function_call'),
                }

    @trace_llm_stream(provider='ollama')
    async def stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from the hosted Ollama service.

        Note: For streaming, do not include the 'stream' flag in payload; the
        service defaults to streamed output.
        """
        # Convert messages to Ollama prompt format
        prompt = ''
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == 'system':
                prompt += f'System: {content}\n'
            elif role == 'user':
                prompt += f'User: {content}\n'
            elif role == 'assistant':
                prompt += f'Assistant: {content}\n'

        # Prepare request payload without 'stream' key for streaming
        payload = {
            'model': self.model,
            'prompt': prompt,
            'temperature': self.temperature,
            **self.kwargs,
        }

        if functions:
            payload['functions'] = functions

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/api/generate', json=payload
            ) as response:
                if response.status != 200:
                    raise Exception(f'Ollama API error: {await response.text()}')

                async for raw_line in response.content:
                    line = raw_line.decode('utf-8').strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        # Skip non-JSON lines
                        continue

                    if 'response' in data and data['response']:
                        yield {'content': data['response']}

                    if data.get('done') is True:
                        break

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        if isinstance(response, dict):
            return response.get('content', '')
        return str(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for Ollama's API"""
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
        """Format tools for Ollama's API"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> str:
        """Format a image in the message"""
        raise NotImplementedError('Not implemented image for LLM Ollama')
