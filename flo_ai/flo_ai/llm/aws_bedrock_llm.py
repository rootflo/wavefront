import json
import re
from typing import Dict, Any, List, AsyncIterator, Optional
import boto3
import asyncio
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


class AWSBedrock(BaseLLM):
    def __init__(
        self,
        model: str = 'openai.gpt-oss-20b-1:0',
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(model=model, temperature=temperature, **kwargs)
        self.boto_client = boto3.client('bedrock-runtime')
        self.model = model
        self.kwargs = kwargs

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        return re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL).strip()

    def _convert_messages(
        self, messages: list[dict], output_schema: dict = None
    ) -> list[dict]:
        result = []

        if output_schema:
            result.append(
                {
                    'role': 'system',
                    'content': f'Provide output in the following JSON schema:\n{json.dumps(output_schema, indent=2)}',
                }
            )

        for msg in messages:
            if msg['role'] == 'function':
                result.append(
                    {
                        'role': 'tool',
                        'tool_call_id': msg.get('tool_use_id', 'unknown'),
                        'content': msg['content'],
                        'name': msg.get('name', ''),
                    }
                )
            else:
                result.append(msg)

        return result

    @trace_llm_call(provider='bedrock')
    async def generate(
        self,
        messages: list[dict],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        converted = self._convert_messages(messages, output_schema)

        request_body: Dict[str, Any] = {
            'model': self.model,
            'messages': converted,
            'temperature': self.temperature,
        }
        if 'max_tokens' in self.kwargs:
            request_body['max_completion_tokens'] = self.kwargs['max_tokens']
        if functions:
            request_body['tools'] = functions

        response = await asyncio.to_thread(
            self.boto_client.invoke_model,
            modelId=self.model,
            body=json.dumps(request_body),
        )
        response_body = json.loads(response['body'].read().decode('utf-8'))

        usage = response_body.get('usage', {})
        if usage:
            llm_metrics.record_tokens(
                total_tokens=usage.get('total_tokens', 0),
                prompt_tokens=usage.get('prompt_tokens', 0),
                completion_tokens=usage.get('completion_tokens', 0),
                model=self.model,
                provider='bedrock',
            )
            tracer = get_tracer()
            if tracer:
                add_span_attributes(
                    trace.get_current_span(),
                    {
                        'llm.tokens.prompt': usage.get('prompt_tokens', 0),
                        'llm.tokens.completion': usage.get('completion_tokens', 0),
                        'llm.tokens.total': usage.get('total_tokens', 0),
                    },
                )

        choices = response_body.get('choices', [])
        if not choices:
            return {'content': '', 'raw_message': response_body}

        message = choices[0].get('message', {})
        if 'content' in message and message['content']:
            message['content'] = self._strip_reasoning(message['content'])
        text_content = message.get('content', '') or ''
        tool_call = None

        tool_calls = message.get('tool_calls', [])
        if tool_calls:
            tc = tool_calls[0]
            tool_call = {
                'name': tc['function']['name'],
                'arguments': tc['function']['arguments'],
                'id': tc['id'],
            }

        if tool_call:
            return {
                'content': text_content,
                'function_call': tool_call,
                'raw_message': message,
            }
        return {'content': text_content, 'raw_message': message}

    @trace_llm_stream(provider='bedrock')
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        converted = self._convert_messages(messages)

        request_body: Dict[str, Any] = {
            'model': self.model,
            'messages': converted,
            'temperature': self.temperature,
            'stream': True,
        }
        if 'max_tokens' in self.kwargs:
            request_body['max_completion_tokens'] = self.kwargs['max_tokens']
        if functions:
            request_body['tools'] = functions

        response = await asyncio.to_thread(
            self.boto_client.invoke_model_with_response_stream,
            modelId=self.model,
            body=json.dumps(request_body),
        )

        buffer = ''

        for event in response['body']:
            chunk_bytes = event.get('chunk', {}).get('bytes', b'')
            if not chunk_bytes:
                continue
            text = chunk_bytes.decode('utf-8').strip()
            # Try direct JSON first (some Bedrock models skip SSE envelope)
            try:
                data = json.loads(text)
                content = data.get('choices', [{}])[0].get('delta', {}).get('content')
                if content:
                    buffer += content
                continue
            except json.JSONDecodeError:
                pass
            # Fall back to SSE format: "data: {...}"
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('data: ') and line != 'data: [DONE]':
                    try:
                        data = json.loads(line[6:])
                        content = (
                            data.get('choices', [{}])[0].get('delta', {}).get('content')
                        )
                        if content:
                            buffer += content
                    except json.JSONDecodeError:
                        pass

        clean = self._strip_reasoning(buffer)
        if clean:
            yield {'content': clean}

    def get_message_content(self, response: Dict[str, Any]) -> str:
        content = (
            response.get('content', '') if isinstance(response, dict) else str(response)
        )
        return self._strip_reasoning(content)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        return {
            'type': 'function',
            'function': {
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
            },
        }

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image: ImageMessageContent) -> dict:
        if image.base64:
            return {
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{image.mime_type or "image/jpeg"};base64,{image.base64}'
                },
            }
        raise NotImplementedError(
            'AWS Bedrock LLM requires image base64 data to format image content.'
        )

    def get_assistant_message_for_tool_call(
        self, response: Dict[str, Any]
    ) -> Optional[Any]:
        if isinstance(response, dict) and 'raw_message' in response:
            return response['raw_message']
        return None

    def get_tool_use_id(self, function_call: Dict[str, Any]) -> Optional[str]:
        return function_call.get('id')

    def format_function_result_message(
        self, function_name: str, content: str, tool_use_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            'role': 'tool',
            'tool_call_id': tool_use_id or 'unknown',
            'content': content,
            'name': function_name,
        }
