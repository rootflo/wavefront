from typing import Any
from .openai_llm import OpenAI


class OpenAIVLLM(OpenAI):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = None,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            temperature=temperature,
            base_url=base_url,
            **kwargs,
        )
        # Store base_url attribute
        self.base_url = base_url

    # overriden
    async def generate(
        self, messages: list[dict], output_schema: dict = None, **kwargs
    ) -> Any:
        # Convert output_schema to OpenAI format if provided
        if output_schema:
            kwargs['response_format'] = {
                'type': 'json_schema',
                'json_schema': {
                    'name': output_schema.get('title', 'default'),
                    'schema': output_schema.get('schema', output_schema),
                },
            }

            # Add JSON format instruction to the system prompt
            if messages and messages[0]['role'] == 'system':
                messages[0]['content'] = (
                    messages[0]['content']
                    + f'\n\nPlease provide your response in JSON format according to the specified schema. \n\n {output_schema}'
                )
            else:
                messages.insert(
                    0,
                    {
                        'role': 'system',
                        'content': f'Please provide your response in JSON format according to the specified schema.\n \n {output_schema}',
                    },
                )

        # Prepare OpenAI API parameters
        vllm_openai_kwargs = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            **kwargs,
            **self.kwargs,
        }

        # Make the API call
        response = await self.client.chat.completions.create(**vllm_openai_kwargs)
        message = response.choices[0].message

        # Return the full message object instead of just the content
        return message
