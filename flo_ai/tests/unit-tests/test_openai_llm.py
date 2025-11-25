#!/usr/bin/env python3
"""
Pytest tests for the OpenAI LLM implementation.
"""

import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.openai_llm import OpenAI
from flo_ai.models.chat_message import ImageMessageContent
from flo_ai.tool.base_tool import Tool


class TestOpenAI:
    """Test class for OpenAI LLM implementation."""

    def test_openai_initialization(self):
        """Test OpenAI LLM initialization with different parameters."""
        # Test with minimal parameters
        llm = OpenAI(api_key='test-key-123')
        assert llm.model == 'gpt-4o-mini'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.7
        assert llm.kwargs == {}

        # Test with custom parameters
        llm = OpenAI(
            model='gpt-4', api_key='test-key-123', temperature=0.5, max_tokens=1000
        )
        assert llm.model == 'gpt-4'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.5
        assert llm.kwargs == {'max_tokens': 1000}

        # Test with base_url
        llm = OpenAI(base_url='https://custom.openai.com', api_key='test-key-123')
        assert llm.client.base_url == 'https://custom.openai.com'

    def test_openai_temperature_handling(self):
        """Test temperature parameter handling."""
        # Test default temperature
        llm = OpenAI(api_key='test-key-123')
        assert llm.temperature == 0.7

        # Test custom temperature
        llm = OpenAI(temperature=0.0, api_key='test-key-123')
        assert llm.temperature == 0.0

        # Test high temperature
        llm = OpenAI(temperature=1.0, api_key='test-key-123')
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        llm = OpenAI(temperature=0.3, custom_temp=0.8, api_key='test-key-123')
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_client_creation(self, mock_async_openai):
        """Test that AsyncOpenAI client is created correctly."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAI(api_key='test-key', base_url='https://custom.com')

        mock_async_openai.assert_called_once_with(
            api_key='test-key', base_url='https://custom.com'
        )
        assert llm.client == mock_client

    @pytest.mark.asyncio
    async def test_openai_generate_basic(self):
        """Test basic generate method without output schema."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        # Mock the client response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = 'Hello, world!'

        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        result = await llm.generate(messages)

        # Verify the API call
        llm.client.chat.completions.create.assert_called_once()
        call_args = llm.client.chat.completions.create.call_args

        assert call_args[1]['model'] == 'gpt-4o-mini'
        assert call_args[1]['messages'] == messages
        assert call_args[1]['temperature'] == 0.7

        # Verify the result
        assert result == mock_response.choices[0].message

    @pytest.mark.asyncio
    async def test_openai_generate_with_output_schema(self):
        """Test generate method with output schema."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        output_schema = {
            'title': 'test_response',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'count': {'type': 'integer'},
                },
            },
        }

        # Mock the client response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"message": "test", "count": 42}'

        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Generate JSON'}]
        await llm.generate(messages, output_schema=output_schema)

        # Verify the API call
        call_args = llm.client.chat.completions.create.call_args[1]

        assert call_args['response_format'] == {'type': 'json_object'}
        assert call_args['functions'] == [
            {'name': 'test_response', 'parameters': output_schema['schema']}
        ]
        assert call_args['function_call'] == {'name': 'test_response'}

        # Verify system message was modified
        assert len(call_args['messages']) == 2
        assert call_args['messages'][0]['role'] == 'system'
        assert 'JSON format' in call_args['messages'][0]['content']

    @pytest.mark.asyncio
    async def test_openai_generate_with_existing_system_message(self):
        """Test generate method with existing system message and output schema."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        output_schema = {'title': 'test', 'schema': {'type': 'object'}}

        # Mock the client response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"test": "value"}'

        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [
            {'role': 'system', 'content': 'You are a helpful assistant'},
            {'role': 'user', 'content': 'Generate JSON'},
        ]

        await llm.generate(messages, output_schema=output_schema)

        # Verify system message was appended to
        call_args = llm.client.chat.completions.create.call_args[1]
        system_message = call_args['messages'][0]['content']
        assert 'You are a helpful assistant' in system_message
        assert 'JSON format' in system_message

    @pytest.mark.asyncio
    async def test_openai_generate_with_kwargs(self):
        """Test generate method with additional kwargs."""
        llm = OpenAI(
            model='gpt-4o-mini', max_tokens=1000, top_p=0.9, api_key='test-key-123'
        )

        # Mock the client response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = 'Response with kwargs'

        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        await llm.generate(messages, stream=False)

        # Verify kwargs were passed through
        call_args = llm.client.chat.completions.create.call_args[1]
        assert call_args['max_tokens'] == 1000
        assert call_args['top_p'] == 0.9
        assert not call_args['stream']

    def test_openai_get_message_content(self):
        """Test get_message_content method."""
        llm = OpenAI(api_key='test-key-123')

        # Test with string response
        result = llm.get_message_content('Hello, world!')
        assert result == 'Hello, world!'

        # Test with message object
        mock_message = Mock()
        mock_message.content = 'Message content'
        result = llm.get_message_content(mock_message)
        assert result == 'Message content'

        # Test with object without content attribute
        mock_obj = Mock()
        del mock_obj.content
        result = llm.get_message_content(mock_obj)
        assert result == str(mock_obj)

    def test_openai_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""
        llm = OpenAI(api_key='test-key-123')

        # Create a mock tool
        tool = Tool(
            name='test_tool',
            description='A test tool',
            function=lambda x: x,
            parameters={
                'param1': {'type': 'string', 'description': 'First parameter'},
                'param2': {'type': 'integer', 'description': 'Second parameter'},
            },
        )

        formatted = llm.format_tool_for_llm(tool)

        assert formatted['name'] == 'test_tool'
        assert formatted['description'] == 'A test tool'
        assert formatted['parameters']['type'] == 'object'
        assert 'param1' in formatted['parameters']['properties']
        assert 'param2' in formatted['parameters']['properties']
        assert formatted['parameters']['required'] == ['param1', 'param2']

    def test_openai_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""
        llm = OpenAI(api_key='test-key-123')

        # Create mock tools
        tool1 = Tool(
            name='tool1',
            description='First tool',
            function=lambda x: x,
            parameters={'param': {'type': 'string', 'description': 'Parameter'}},
        )

        tool2 = Tool(
            name='tool2',
            description='Second tool',
            function=lambda x: x,
            parameters={'param': {'type': 'integer', 'description': 'Parameter'}},
        )

        formatted = llm.format_tools_for_llm([tool1, tool2])

        assert len(formatted) == 2
        assert formatted[0]['name'] == 'tool1'
        assert formatted[1]['name'] == 'tool2'

    def test_openai_format_image_in_message(self):
        """Test format_image_in_message method."""
        llm = OpenAI(api_key='test-key-123')

        # Test with URL (should work)
        image = ImageMessageContent(
            url='https://example.com/image.jpg', mime_type='image/jpeg'
        )
        result = llm.format_image_in_message(image)

        assert result is not None
        assert result['type'] == 'input_image'
        assert result['image']['url'] == 'https://example.com/image.jpg'

    @pytest.mark.asyncio
    async def test_openai_generate_error_handling(self):
        """Test error handling in generate method."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        # Mock client to raise an exception
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(
            side_effect=Exception('API Error')
        )

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='API Error'):
            await llm.generate(messages)

    def test_openai_model_parameter_handling(self):
        """Test that model parameter is properly handled."""
        test_models = ['gpt-4', 'gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo']

        for model in test_models:
            llm = OpenAI(model=model, api_key='test-key-123')
            assert llm.model == model

    def test_openai_api_key_handling(self):
        """Test API key handling."""
        # Test with API key
        llm = OpenAI(api_key='secret-key-123')
        assert llm.api_key == 'secret-key-123'

        # Test with empty string API key
        llm = OpenAI(api_key='')
        assert llm.api_key == ''

    def test_openai_base_url_handling(self):
        """Test base URL handling."""
        # Test with base URL
        llm = OpenAI(base_url='https://custom.openai.com', api_key='test-key-123')
        assert llm.client.base_url == 'https://custom.openai.com'

        # Test without base URL
        llm = OpenAI(api_key='test-key-123')
        assert not hasattr(llm, 'base_url')

    @pytest.mark.asyncio
    async def test_openai_stream_basic(self):
        """Test basic stream method without functions."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        # Mock streaming chunks
        mock_delta1 = Mock()
        mock_delta1.content = 'Hello'

        mock_delta2 = Mock()
        mock_delta2.content = ', world!'

        mock_choice1 = Mock()
        mock_choice1.delta = mock_delta1

        mock_choice2 = Mock()
        mock_choice2.delta = mock_delta2

        mock_chunk1 = Mock()
        mock_chunk1.choices = [mock_choice1]

        mock_chunk2 = Mock()
        mock_chunk2.choices = [mock_choice2]

        # Create a proper async iterator
        async def async_iter():
            yield mock_chunk1
            yield mock_chunk2

        # Mock the client response
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=async_iter())

        messages = [{'role': 'user', 'content': 'Hello'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages):
            results.append(chunk)

        # Verify the API call
        llm.client.chat.completions.create.assert_called_once()
        call_args = llm.client.chat.completions.create.call_args

        assert call_args[1]['model'] == 'gpt-4o-mini'
        assert call_args[1]['messages'] == messages
        assert call_args[1]['temperature'] == 0.7
        assert call_args[1]['stream'] is True

        # Verify the streaming results
        assert len(results) == 2
        assert results[0] == {'content': 'Hello'}
        assert results[1] == {'content': ', world!'}

    @pytest.mark.asyncio
    async def test_openai_stream_with_functions(self):
        """Test stream method with functions."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

        # Mock streaming chunks
        mock_delta = Mock()
        mock_delta.content = 'I will use the function'

        mock_choice = Mock()
        mock_choice.delta = mock_delta

        mock_chunk = Mock()
        mock_chunk.choices = [mock_choice]

        # Create a proper async iterator
        async def async_iter():
            yield mock_chunk

        # Mock the client response
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=async_iter())

        messages = [{'role': 'user', 'content': 'Use the function'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages, functions=functions):
            results.append(chunk)

        # Verify functions were passed correctly
        call_args = llm.client.chat.completions.create.call_args
        assert call_args[1]['functions'] == functions

        # Verify the streaming results
        assert len(results) == 1
        assert results[0] == {'content': 'I will use the function'}

    @pytest.mark.asyncio
    async def test_openai_stream_error_handling(self):
        """Test error handling in stream method."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        # Mock client to raise an exception
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(
            side_effect=Exception('Streaming API Error')
        )

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='Streaming API Error'):
            async for chunk in llm.stream(messages):
                pass
