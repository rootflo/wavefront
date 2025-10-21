#!/usr/bin/env python3
"""
Pytest tests for the Anthropic LLM implementation.
"""

import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.llm.base_llm import ImageMessage
from flo_ai.tool.base_tool import Tool


class TestAnthropic:
    """Test class for Anthropic LLM implementation."""

    def test_anthropic_initialization(self):
        """Test Anthropic LLM initialization with different parameters."""
        # Test with minimal parameters
        llm = Anthropic()
        assert llm.model == 'claude-3-5-sonnet-20240620'
        assert llm.api_key is None
        assert llm.temperature == 0.7
        assert llm.kwargs == {}

        # Test with custom parameters
        llm = Anthropic(
            model='claude-3-opus-20240229',
            api_key='test-key-123',
            temperature=0.5,
            max_tokens=1000,
        )
        assert llm.model == 'claude-3-opus-20240229'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.5
        assert llm.kwargs == {'max_tokens': 1000}

        # Test with base_url
        llm = Anthropic(base_url='https://custom.anthropic.com')
        assert llm.client.base_url == 'https://custom.anthropic.com'

    def test_anthropic_temperature_handling(self):
        """Test temperature parameter handling."""
        # Test default temperature
        llm = Anthropic()
        assert llm.temperature == 0.7

        # Test custom temperature
        llm = Anthropic(temperature=0.0)
        assert llm.temperature == 0.0

        # Test high temperature
        llm = Anthropic(temperature=1.0)
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        llm = Anthropic(temperature=0.3, custom_temp=0.8)
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    @patch('flo_ai.llm.anthropic_llm.AsyncAnthropic')
    def test_anthropic_client_creation(self, mock_async_anthropic):
        """Test that AsyncAnthropic client is created correctly."""
        mock_client = Mock()
        mock_async_anthropic.return_value = mock_client

        llm = Anthropic(api_key='test-key', base_url='https://custom.com')

        mock_async_anthropic.assert_called_once_with(
            api_key='test-key', base_url='https://custom.com'
        )
        assert llm.client == mock_client

    @pytest.mark.asyncio
    async def test_anthropic_generate_basic(self):
        """Test basic generate method without functions or output schema."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        # Mock the client response
        mock_content = Mock()
        mock_content.text = 'Hello, world!'
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        result = await llm.generate(messages)

        # Verify the API call
        llm.client.messages.create.assert_called_once()
        call_args = llm.client.messages.create.call_args

        assert call_args[1]['model'] == 'claude-3-5-sonnet-20240620'
        assert call_args[1]['messages'] == messages
        assert call_args[1]['temperature'] == 0.7

        # Verify the result
        assert result == {'content': 'Hello, world!'}

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_system_message(self):
        """Test generate method with system message."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        # Mock the client response
        mock_content = Mock()
        mock_content.text = "I'm a helpful assistant"
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [
            {'role': 'system', 'content': 'You are a helpful assistant'},
            {'role': 'user', 'content': 'Hello'},
        ]

        await llm.generate(messages)

        # Verify system message was passed correctly
        call_args = llm.client.messages.create.call_args[1]
        assert call_args['system'] == 'You are a helpful assistant'

        # Verify conversation messages don't include system
        conversation_messages = call_args['messages']
        assert len(conversation_messages) == 1
        assert conversation_messages[0]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_output_schema(self):
        """Test generate method with output schema."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        output_schema = {
            'type': 'object',
            'properties': {'message': {'type': 'string'}, 'count': {'type': 'integer'}},
        }

        # Mock the client response
        mock_content = Mock()
        mock_content.text = '{"message": "test", "count": 42}'
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Generate JSON'}]
        await llm.generate(messages, output_schema=output_schema)

        # Verify system message includes output schema
        call_args = llm.client.messages.create.call_args[1]
        system_message = call_args['system']
        assert 'Provide output in the following JSON schema' in system_message
        assert 'message' in system_message
        assert 'count' in system_message

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_functions(self):
        """Test generate method with functions (tools)."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        functions = [
            {
                'type': 'custom',
                'name': 'test_function',
                'description': 'A test function',
                'input_schema': {'type': 'object'},
            }
        ]

        # Mock the client response
        mock_content = Mock()
        mock_content.text = "I'll use the function"
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the function'}]
        await llm.generate(messages, functions=functions)

        # Verify functions were passed correctly
        call_args = llm.client.messages.create.call_args[1]
        assert call_args['tools'] == functions

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_tool_use(self):
        """Test generate method when Claude uses a tool."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        # Mock the client response with tool use
        mock_tool_content = Mock()
        mock_tool_content.type = 'tool_use'
        mock_tool_content.name = 'test_tool'
        mock_tool_content.input = {'param': 'value'}

        mock_text_content = Mock()
        mock_text_content.text = 'I used the tool'
        mock_text_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_text_content, mock_tool_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the tool'}]
        result = await llm.generate(messages)

        # Verify tool use was detected and formatted correctly
        assert 'function_call' in result
        assert result['function_call']['name'] == 'test_tool'
        assert result['function_call']['arguments'] == '{"param": "value"}'

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_max_tokens(self):
        """Test generate method with max_tokens parameter."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620', max_tokens=1000)

        # Mock the client response
        mock_content = Mock()
        mock_content.text = 'Response with max tokens'
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        await llm.generate(messages)

        # Verify max_tokens was passed
        call_args = llm.client.messages.create.call_args[1]
        assert call_args['max_tokens'] == 1000

    @pytest.mark.asyncio
    async def test_anthropic_generate_with_kwargs(self):
        """Test generate method with additional kwargs."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620', top_p=0.9)

        # Mock the client response
        mock_content = Mock()
        mock_content.text = 'Response with kwargs'
        mock_content.type = 'text'

        mock_response = Mock()
        mock_response.content = [mock_content]

        llm.client = Mock()
        llm.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        await llm.generate(messages)

        # Verify kwargs were passed through
        call_args = llm.client.messages.create.call_args[1]
        assert call_args['top_p'] == 0.9

    def test_anthropic_get_message_content(self):
        """Test get_message_content method."""
        llm = Anthropic()

        # Test with dict response
        response = {'content': 'Hello, world!'}
        result = llm.get_message_content(response)
        assert result == 'Hello, world!'

        # Test with string response
        result = llm.get_message_content('Direct string')
        assert result == 'Direct string'

        # Test with empty content
        response = {'content': ''}
        result = llm.get_message_content(response)
        assert result == ''

    def test_anthropic_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""
        llm = Anthropic()

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

        assert formatted['type'] == 'custom'
        assert formatted['name'] == 'test_tool'
        assert formatted['description'] == 'A test tool'
        assert formatted['input_schema']['type'] == 'object'
        assert 'param1' in formatted['input_schema']['properties']
        assert 'param2' in formatted['input_schema']['properties']
        assert formatted['input_schema']['required'] == ['param1', 'param2']

    def test_anthropic_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""
        llm = Anthropic()

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
        assert all(tool['type'] == 'custom' for tool in formatted)

    def test_anthropic_format_image_in_message(self):
        """Test format_image_in_message method."""
        llm = Anthropic()

        # This method is not implemented yet
        image = ImageMessage(image_url='https://example.com/image.jpg')

        with pytest.raises(NotImplementedError):
            llm.format_image_in_message(image)

    @pytest.mark.asyncio
    async def test_anthropic_generate_error_handling(self):
        """Test error handling in generate method."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        # Mock client to raise an exception
        llm.client = Mock()
        llm.client.messages.create = AsyncMock(side_effect=Exception('API Error'))

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='Error in Claude API call: API Error'):
            await llm.generate(messages)

    def test_anthropic_model_parameter_handling(self):
        """Test that model parameter is properly handled."""
        test_models = [
            'claude-3-5-sonnet-20240620',
            'claude-3-opus-20240229',
            'claude-3-sonnet-20240229',
            'claude-3-haiku-20240307',
        ]

        for model in test_models:
            llm = Anthropic(model=model)
            assert llm.model == model

    def test_anthropic_api_key_handling(self):
        """Test API key handling."""
        # Test with API key
        llm = Anthropic(api_key='secret-key-123')
        assert llm.api_key == 'secret-key-123'

        # Test without API key
        llm = Anthropic()
        assert llm.api_key is None

        # Test with empty string API key
        llm = Anthropic(api_key='')
        assert llm.api_key == ''

    def test_anthropic_base_url_handling(self):
        """Test base URL handling."""
        # Test with base URL
        llm = Anthropic(base_url='https://custom.anthropic.com')
        assert llm.client.base_url == 'https://custom.anthropic.com'

        # Test without base URL
        llm = Anthropic()
        assert not hasattr(llm, 'base_url')

    @pytest.mark.asyncio
    async def test_anthropic_stream_basic(self):
        """Test basic stream method without functions."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        # Mock streaming events
        mock_delta1 = Mock()
        mock_delta1.type = 'text_delta'
        mock_delta1.text = 'Hello'

        mock_delta2 = Mock()
        mock_delta2.type = 'text_delta'
        mock_delta2.text = ', world!'

        mock_event1 = Mock()
        mock_event1.type = 'content_block_delta'
        mock_event1.delta = mock_delta1

        mock_event2 = Mock()
        mock_event2.type = 'content_block_delta'
        mock_event2.delta = mock_delta2

        # Create a proper async iterator
        async def async_iter():
            yield mock_event1
            yield mock_event2

        # Mock the streaming context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.__aiter__ = Mock(return_value=async_iter())

        llm.client = Mock()
        llm.client.messages.stream = Mock(return_value=mock_stream)

        messages = [{'role': 'user', 'content': 'Hello'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages):
            results.append(chunk)

        # Verify the API call
        llm.client.messages.stream.assert_called_once()
        call_args = llm.client.messages.stream.call_args[1]

        assert call_args['model'] == 'claude-3-5-sonnet-20240620'
        assert call_args['messages'] == messages
        assert call_args['temperature'] == 0.7
        assert call_args['max_tokens'] == 1024

        # Verify the streaming results
        assert len(results) == 2
        assert results[0] == {'content': 'Hello'}
        assert results[1] == {'content': ', world!'}

    @pytest.mark.asyncio
    async def test_anthropic_stream_with_functions(self):
        """Test stream method with functions (tools)."""
        llm = Anthropic(model='claude-3-5-sonnet-20240620')

        functions = [
            {
                'type': 'custom',
                'name': 'test_function',
                'description': 'A test function',
                'input_schema': {'type': 'object'},
            }
        ]

        # Mock streaming events
        mock_delta = Mock()
        mock_delta.type = 'text_delta'
        mock_delta.text = 'I will use the function'

        mock_event = Mock()
        mock_event.type = 'content_block_delta'
        mock_event.delta = mock_delta

        # Create a proper async iterator
        async def async_iter():
            yield mock_event

        # Mock the streaming context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.__aiter__ = Mock(return_value=async_iter())

        llm.client = Mock()
        llm.client.messages.stream = Mock(return_value=mock_stream)

        messages = [{'role': 'user', 'content': 'Use the function'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages, functions=functions):
            results.append(chunk)

        # Verify functions were passed correctly
        call_args = llm.client.messages.stream.call_args[1]
        assert call_args['tools'] == functions

        # Verify the streaming results
        assert len(results) == 1
        assert results[0] == {'content': 'I will use the function'}
