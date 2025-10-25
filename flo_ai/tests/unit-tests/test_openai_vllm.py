#!/usr/bin/env python3
"""
Pytest tests for the OpenAI VLLM implementation.
"""

import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.openai_vllm import OpenAIVLLM
from flo_ai.llm.base_llm import ImageMessage
from flo_ai.tool.base_tool import Tool


class TestOpenAIVLLM:
    """Test class for OpenAI VLLM implementation."""

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_initialization(self, mock_async_openai):
        """Test OpenAI VLLM initialization with different parameters."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # Test with minimal parameters
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )
        assert llm.model == 'gpt-4o-mini'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.7
        assert llm.base_url == 'https://api.vllm.com'
        assert llm.kwargs == {}

        # Test with custom parameters
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://custom.vllm.com',
            model='gpt-4',
            api_key='test-key-123',
            temperature=0.5,
            max_tokens=1000,
        )
        assert llm.model == 'gpt-4'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.5
        assert llm.base_url == 'https://custom.vllm.com'
        assert llm.kwargs == {'max_tokens': 1000}

        # Test with additional kwargs
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            max_tokens=1000,
            top_p=0.9,
            api_key='test-key-123',
        )
        assert llm.kwargs == {'max_tokens': 1000, 'top_p': 0.9}

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_temperature_handling(self, mock_async_openai):
        """Test temperature parameter handling."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # Test default temperature
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )
        assert llm.temperature == 0.7

        # Test custom temperature
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            temperature=0.0,
            api_key='test-key-123',
        )
        assert llm.temperature == 0.0

        # Test high temperature
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            temperature=1.0,
            api_key='test-key-123',
        )
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            temperature=0.3,
            custom_temp=0.8,
            api_key='test-key-123',
        )
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_client_creation(self, mock_async_openai):
        """Test that AsyncOpenAI client is created correctly with VLLM parameters."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://custom.vllm.com',
            model='gpt-4o-mini',
            api_key='test-key-123',
        )

        mock_async_openai.assert_called_once_with(
            api_key='test-key-123', base_url='https://custom.vllm.com'
        )
        assert llm.client == mock_client

        # Test without API key
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        mock_async_openai.assert_called_once_with(
            api_key='test-key-123', base_url='https://api.vllm.com'
        )
        assert llm.client == mock_client

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_generate_basic(self, mock_async_openai):
        """Test basic generate method without output schema."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Mock the client response
        mock_choice = Mock()
        mock_choice.message.content = 'Hello, world!'

        mock_response = Mock()
        mock_response.choices = [mock_choice]

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
        assert result.content == 'Hello, world!'

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_generate_with_output_schema(self, mock_async_openai):
        """Test generate method with output schema."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        output_schema = {
            'title': 'test_schema',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'count': {'type': 'integer'},
                },
            },
        }

        # Mock the client response
        mock_choice = Mock()
        mock_choice.message.content = '{"message": "test", "count": 42}'

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Generate JSON'}]
        result = await llm.generate(messages, output_schema=output_schema)

        # Verify output schema was configured
        call_args = llm.client.chat.completions.create.call_args
        assert call_args[1]['response_format']['type'] == 'json_schema'
        assert call_args[1]['response_format']['json_schema']['name'] == 'test_schema'

        # Verify the result
        assert result.content == '{"message": "test", "count": 42}'

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_generate_with_existing_system_message(
        self, mock_async_openai
    ):
        """Test generate method with existing system message and output schema."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        output_schema = {'title': 'test_schema', 'schema': {'type': 'object'}}

        # Mock the client response
        mock_choice = Mock()
        mock_choice.message.content = '{"result": "success"}'

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [
            {'role': 'system', 'content': 'You are a helpful assistant'},
            {'role': 'user', 'content': 'Generate JSON'},
        ]

        result = await llm.generate(messages, output_schema=output_schema)

        # Verify system message was updated
        call_args = llm.client.chat.completions.create.call_args
        updated_messages = call_args[1]['messages']
        assert updated_messages[0]['role'] == 'system'
        assert 'JSON format' in updated_messages[0]['content']
        assert 'test_schema' in updated_messages[0]['content']

        # Verify the result
        assert result.content == '{"result": "success"}'

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_generate_with_kwargs(self, mock_async_openai):
        """Test generate method with additional kwargs."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            top_p=0.9,
            max_output_tokens=1000,
            api_key='test-key-123',
        )

        # Mock the client response
        mock_choice = Mock()
        mock_choice.message.content = 'Response with kwargs'

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        llm.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        result = await llm.generate(messages)

        # Verify kwargs were passed through
        call_args = llm.client.chat.completions.create.call_args
        assert call_args[1]['top_p'] == 0.9
        assert call_args[1]['max_output_tokens'] == 1000

        # Verify the result
        assert result.content == 'Response with kwargs'

    def test_openai_vllm_get_message_content(self):
        """Test get_message_content method."""
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Test with dict response (should return str representation)
        response = {'content': 'Hello, world!'}
        result = llm.get_message_content(response)
        assert result == "{'content': 'Hello, world!'}"

        # Test with string response
        result = llm.get_message_content('Direct string')
        assert result == 'Direct string'

        # Test with empty content
        response = {'content': ''}
        result = llm.get_message_content(response)
        assert result == "{'content': ''}"

        # Test with message object that has content attribute
        mock_message = Mock()
        mock_message.content = 'Message content'
        result = llm.get_message_content(mock_message)
        assert result == 'Message content'

    def test_openai_vllm_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

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

    def test_openai_vllm_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

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

    def test_openai_vllm_format_image_in_message(self):
        """Test format_image_in_message method."""
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Test with image message
        image = ImageMessage(image_url='https://example.com/image.jpg')

        with pytest.raises(
            NotImplementedError, match='Not implemented image for LLM OpenAI'
        ):
            llm.format_image_in_message(image)

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_generate_error_handling(self, mock_async_openai):
        """Test error handling in generate method."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Mock client to raise an exception
        llm.client.chat.completions.create = AsyncMock(
            side_effect=Exception('API Error')
        )

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='API Error'):
            await llm.generate(messages)

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_model_parameter_handling(self, mock_async_openai):
        """Test that model parameter is properly handled."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        test_models = ['gpt-4', 'gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo']

        for model in test_models:
            mock_async_openai.reset_mock()
            llm = OpenAIVLLM(
                base_url='https://api.vllm.com', model=model, api_key='test-key-123'
            )
            assert llm.model == model

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_api_key_handling(self, mock_async_openai):
        """Test API key handling."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # Test with API key
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            api_key='secret-key-123',
        )
        assert llm.api_key == 'secret-key-123'

        # Test without API key
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )
        assert llm.api_key == 'test-key-123'

        # Test with empty string API key
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key=''
        )
        assert llm.api_key == ''

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_base_url_handling(self, mock_async_openai):
        """Test base URL handling."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # Test with base URL
        llm = OpenAIVLLM(
            base_url='https://custom.vllm.com',
            model='gpt-4o-mini',
            api_key='test-key-123',
        )
        assert llm.base_url == 'https://custom.vllm.com'

        # Test with different base URL
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://another.vllm.com',
            model='gpt-4o-mini',
            api_key='test-key-123',
        )
        assert llm.base_url == 'https://another.vllm.com'

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_inheritance_from_openai(self, mock_async_openai):
        """Test that OpenAIVLLM inherits from OpenAI."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Should inherit from OpenAI
        from flo_ai.llm.openai_llm import OpenAI

        assert isinstance(llm, OpenAI)

        # Should have all the methods from OpenAI
        assert hasattr(llm, 'generate')
        assert hasattr(llm, 'get_message_content')
        assert hasattr(llm, 'format_tool_for_llm')
        assert hasattr(llm, 'format_tools_for_llm')
        assert hasattr(llm, 'format_image_in_message')

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_parameter_combinations(self, mock_async_openai):
        """Test various parameter combinations."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # Test with all parameters
        llm = OpenAIVLLM(
            model='gpt-4',
            api_key='key123',
            temperature=0.3,
            base_url='https://custom.com',
            max_tokens=500,
            top_p=0.8,
        )

        assert llm.model == 'gpt-4'
        assert llm.api_key == 'key123'
        assert llm.temperature == 0.3
        assert llm.base_url == 'https://custom.com'
        assert llm.kwargs == {'max_tokens': 500, 'top_p': 0.8}

        # Test with minimal parameters
        mock_async_openai.reset_mock()
        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        assert llm.model == 'gpt-4o-mini'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.7
        assert llm.base_url == 'https://api.vllm.com'
        assert llm.kwargs == {}

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_method_inheritance(self, mock_async_openai):
        """Test that OpenAIVLLM inherits all methods from OpenAI."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Test that OpenAIVLLM has all the methods from OpenAI
        assert hasattr(llm, 'generate')
        assert hasattr(llm, 'get_message_content')
        assert hasattr(llm, 'format_tool_for_llm')
        assert hasattr(llm, 'format_tools_for_llm')
        assert hasattr(llm, 'format_image_in_message')

        # Should be callable
        assert callable(llm.generate)
        assert callable(llm.get_message_content)
        assert callable(llm.format_tool_for_llm)
        assert callable(llm.format_tools_for_llm)
        assert callable(llm.format_image_in_message)

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_default_values(self, mock_async_openai):
        """Test that default values are set correctly."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Default values from OpenAI
        assert llm.model == 'gpt-4o-mini'
        assert llm.temperature == 0.7

        # Default values from BaseLLM
        assert llm.api_key == 'test-key-123'
        assert llm.kwargs == {}

        # Default values from OpenAIVLLM
        assert llm.base_url == 'https://api.vllm.com'

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_parameter_override(self, mock_async_openai):
        """Test that parameters can be overridden after initialization."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Change parameters
        llm.model = 'new-model'
        llm.temperature = 0.1
        llm.base_url = 'new-url'

        # Verify changes
        assert llm.model == 'new-model'
        assert llm.temperature == 0.1
        assert llm.base_url == 'new-url'

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_kwargs_storage(self, mock_async_openai):
        """Test that additional kwargs are properly stored."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com',
            model='gpt-4o-mini',
            max_tokens=1000,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1,
            api_key='test-key-123',
        )

        assert 'max_tokens' in llm.kwargs
        assert 'top_p' in llm.kwargs
        assert 'frequency_penalty' in llm.kwargs
        assert 'presence_penalty' in llm.kwargs
        assert llm.kwargs['max_tokens'] == 1000
        assert llm.kwargs['top_p'] == 0.9

    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    def test_openai_vllm_initialization_order(self, mock_async_openai):
        """Test that initialization happens in the correct order."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        # This should not raise an error
        llm = OpenAIVLLM(
            model='test-model',
            base_url='https://test.vllm.com',
            project='test-project',
            location='test-location',
            api_key='test-key-123',
        )

        # Verify all attributes are set correctly
        assert llm.model == 'test-model'
        assert llm.base_url == 'https://test.vllm.com'
        assert llm.client == mock_client

    @pytest.mark.asyncio
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_stream_basic(self, mock_async_openai):
        """Test basic stream method without functions."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

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
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_stream_with_functions(self, mock_async_openai):
        """Test stream method with functions."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

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
    @patch('flo_ai.llm.openai_llm.AsyncOpenAI')
    async def test_openai_vllm_stream_error_handling(self, mock_async_openai):
        """Test error handling in stream method."""
        mock_client = Mock()
        mock_async_openai.return_value = mock_client

        llm = OpenAIVLLM(
            base_url='https://api.vllm.com', model='gpt-4o-mini', api_key='test-key-123'
        )

        # Mock client to raise an exception
        llm.client.chat.completions.create = AsyncMock(
            side_effect=Exception('Streaming API Error')
        )

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='Streaming API Error'):
            async for chunk in llm.stream(messages):
                pass
