from typing import Dict, Any, List, Optional
from anthropic import AsyncAnthropic
import json
from .base_llm import BaseLLM, ImageMessage
from flo_ai.tool.base_tool import Tool


class Anthropic(BaseLLM):
    def __init__(
        self,
        model: str = 'claude-3-5-sonnet-20240620',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: str = None,
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        self.client = AsyncAnthropic(api_key=self.api_key, base_url=base_url)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
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
                conversation.append(
                    {
                        'role': 'assistant' if msg['role'] == 'assistant' else 'user',
                        'content': msg['content'],
                    }
                )

        try:
            kwargs = {
                'model': self.model,
                'messages': conversation,
                'temperature': self.temperature,
                **self.kwargs,
            }

            if system_message:
                kwargs['system'] = system_message

            if functions:
                kwargs['tools'] = functions

            response = await self.client.messages.create(**kwargs)

            # Check if there's a tool use in the response
            for content_block in response.content:
                if content_block.type == 'tool_use':
                    return {
                        'content': response.content[0].text if response.content else '',
                        'function_call': {
                            'name': content_block.name,
                            'arguments': json.dumps(content_block.input),
                        },
                    }

            # Handle regular text response
            return {'content': response.content[0].text if response.content else ''}

        except Exception as e:
            raise Exception(f'Error in Claude API call: {str(e)}')

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

    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        raise NotImplementedError('Not implemented image for LLM Anthropic')
