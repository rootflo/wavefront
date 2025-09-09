from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from .base_llm import BaseLLM, ImageMessage
from flo_ai.tool.base_tool import Tool


class Gemini(BaseLLM):
    def __init__(
        self,
        model: str = 'gemini-2.5-flash',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: str = None,
        **kwargs,
    ):
        super().__init__(model, api_key, temperature, **kwargs)
        self.client = (
            genai.Client(api_key=self.api_key) if self.api_key else genai.Client()
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
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
            generation_config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=system_prompt,
                **self.kwargs,
            )

            # Add tools if functions are provided
            if functions:
                tools = types.Tool(function_declarations=functions)
                generation_config.tools = [tools]

            # Add structured output configuration if output_schema is provided
            if output_schema:
                generation_config.response_mime_type = 'application/json'
                generation_config.response_schema = output_schema

            # Make the API call
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=generation_config,
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

    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        if image.image_file_path:
            with open(image.image_file_path, 'rb') as image_file:
                image_bytes = image_file.read()
            return types.Part.from_bytes(
                data=image_bytes,
                mime_type=image.mime_type,
            )
        elif image.image_bytes:
            return types.Part.from_bytes(
                data=image.image_bytes,
                mime_type=image.mime_type,
            )
        raise NotImplementedError(
            'Not other way other than file path has been implemented'
        )
