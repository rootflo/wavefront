from typing import Dict, Any, List
from openai import AsyncOpenAI
from .base_llm import BaseLLM, ImageMessage
from flo_ai.tool.base_tool import Tool


class OpenAI(BaseLLM):
    def __init__(
        self,
        model='gpt-4o-mini',
        api_key: str = None,
        temperature: float = 0.7,
        base_url: str = None,
        **kwargs,
    ):
        super().__init__(
            model=model, api_key=api_key, temperature=temperature, **kwargs
        )
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.kwargs = kwargs

    async def generate(
        self, messages: list[dict], output_schema: dict = None, **kwargs
    ) -> Any:
        # Convert output_schema to OpenAI format if provided
        if output_schema:
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

        # Prepare OpenAI API parameters
        openai_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            **kwargs,
            **self.kwargs,
        }

        # Make the API call
        response = await self.client.chat.completions.create(**openai_kwargs)
        message = response.choices[0].message

        # Return the full message object instead of just the content
        return message

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

    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        raise NotImplementedError('Not implemented image for LLM OpenAI')
