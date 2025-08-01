from typing import Dict, Any, List, Optional
from google import genai
import json
from .base_llm import BaseLLM, ImageMessage
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.logger import logger


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
        # Gemini uses a simple content string format
        contents = []
        system_prompt = ''
        for msg in messages:
            role = msg['role']
            message_content = msg['content']

            if role == 'system':
                system_prompt += f'{message_content}\n'
            else:
                contents.append(message_content)

        # Add output schema instruction if provided
        if output_schema:
            contents += f'\nPlease provide your response in JSON format according to this schema:\n{json.dumps(output_schema, indent=2)}\n'

        # Add function information if provided
        if functions:
            contents += f'\nAvailable functions:\n{json.dumps(functions, indent=2)}\n'

        try:
            # Prepare generation config
            generation_config = genai.types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=system_prompt,
                **self.kwargs,
            )

            # Make the API call
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=generation_config if generation_config else None,
            )

            # Check if response contains function call information
            # For now, we'll assume text response and parse for function calls if needed
            response_text = (
                response.text if hasattr(response, 'text') else str(response)
            )

            # Try to detect function calls in the response
            # This is a simple implementation - in practice, you might need more sophisticated parsing
            if functions and self._is_function_call_response(response_text):
                function_call = self._parse_function_call(response_text)
                if function_call:
                    return {
                        'content': response_text,
                        'function_call': function_call,
                    }

            return {'content': response_text}

        except Exception as e:
            raise Exception(f'Error in Gemini API call: {str(e)}')

    def _is_function_call_response(self, response_text: str) -> bool:
        """Check if the response contains a function call"""
        # Simple heuristic - look for function call patterns
        return (
            'function_call' in response_text.lower()
            or '(' in response_text
            and ')' in response_text
        )

    def _parse_function_call(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse function call from response text"""
        # This is a simplified parser - in practice, you'd want more robust parsing
        try:
            # Look for JSON-like function call structure
            if '{' in response_text and '}' in response_text:
                # Extract JSON-like content
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_str = response_text[start:end]
                parsed = json.loads(json_str)

                if 'name' in parsed and 'arguments' in parsed:
                    return {
                        'name': parsed['name'],
                        'arguments': json.dumps(parsed['arguments']),
                    }
        except Exception as e:
            logger.error(f'Error parsing function call: {str(e)}')
        return None

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        if isinstance(response, dict):
            return response.get('content', '')
        return str(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a single tool for Gemini's API"""
        return {
            'name': tool.name,
            'description': tool.description,
            'parameters': {
                'type': 'object',
                'properties': {
                    name: {
                        'type': info.get('type', 'string'),
                        'description': info.get('description', ''),
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
        """Format tools for Gemini's API"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        if image.image_file_path:
            with open(image.image_file_path, 'rb') as image_file:
                image_bytes = image_file.read()
            return genai.types.Part.from_bytes(
                data=image_bytes,
                mime_type=image.mime_type,
            )
        elif image.image_bytes:
            return genai.types.Part.from_bytes(
                data=image.image_bytes,
                mime_type=image.mime_type,
            )
        raise NotImplementedError(
            'Not other way other than file path has been implemented'
        )
