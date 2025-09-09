from typing import Dict, Any, List, Optional
import aiohttp
import json
from .base_llm import BaseLLM, ImageMessage
from flo_ai.tool.base_tool import Tool


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

    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        raise NotImplementedError('Not implemented image for LLM Ollama')
