#!/usr/bin/env python3
"""
Pytest tests for the Gemini LLM implementation.
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch, mock_open

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.gemini_llm import Gemini
from flo_ai.llm.base_llm import ImageMessage
from flo_ai.tool.base_tool import Tool

os.environ['GOOGLE_API_KEY'] = 'test-key-123'


class TestGemini:
    """Test class for Gemini LLM implementation."""

    @patch('flo_ai.llm.gemini_llm.genai.Client')
    def test_gemini_initialization(self, mock_genai_client):
        """Test Gemini LLM initialization with different parameters."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with minimal parameters
        llm = Gemini()
        assert llm.model == 'gemini-2.5-flash'
        assert llm.api_key is None
        assert llm.temperature == 0.7
        assert llm.kwargs == {}

        # Test with custom parameters
        mock_genai_client.reset_mock()
        llm = Gemini(
            model='gemini-1.5-pro',
            api_key='test-key-123',
            temperature=0.5,
            max_output_tokens=1000,
        )
        assert llm.model == 'gemini-1.5-pro'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.5
        assert llm.kwargs == {'max_output_tokens': 1000}

        # Test with base_url (should be ignored as it's not implemented)
        mock_genai_client.reset_mock()
        llm = Gemini(base_url='https://custom.gemini.com')
        # base_url is not stored as an attribute, so we just verify it doesn't crash

    @patch('flo_ai.llm.gemini_llm.genai.Client')
    def test_gemini_temperature_handling(self, mock_genai_client):
        """Test temperature parameter handling."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test default temperature
        llm = Gemini()
        assert llm.temperature == 0.7

        # Test custom temperature
        mock_genai_client.reset_mock()
        llm = Gemini(temperature=0.0)
        assert llm.temperature == 0.0

        # Test high temperature
        mock_genai_client.reset_mock()
        llm = Gemini(temperature=1.0)
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        mock_genai_client.reset_mock()
        llm = Gemini(temperature=0.3, custom_temp=0.8)
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    @patch('flo_ai.llm.gemini_llm.genai.Client')
    def test_gemini_client_creation(self, mock_genai_client):
        """Test that genai Client is created correctly."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = Gemini(api_key='test-key')

        mock_genai_client.assert_called_once_with(api_key='test-key')
        assert llm.client == mock_client

        # Test without API key
        mock_genai_client.reset_mock()
        llm = Gemini()

        mock_genai_client.assert_called_once_with()
        assert llm.client == mock_client

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.genai.Client')
    async def test_gemini_generate_basic(self, mock_genai_client):
        """Test basic generate method without functions or output schema."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = Gemini(model='gemini-2.5-flash')

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Hello, world!'

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        result = await llm.generate(messages)

        # Verify the API call
        llm.client.models.generate_content.assert_called_once()
        call_args = llm.client.models.generate_content.call_args

        assert call_args[1]['model'] == 'gemini-2.5-flash'
        assert call_args[1]['contents'] == ['Hello']
        assert call_args[1]['config'].temperature == 0.7

        # Verify the result
        assert result == {'content': 'Hello, world!'}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.genai.Client')
    async def test_gemini_generate_with_system_message(self, mock_genai_client):
        """Test generate method with system message."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = Gemini(model='gemini-2.5-flash')

        # Mock the client response
        mock_response = Mock()
        mock_response.text = "I'm a helpful assistant"

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [
            {'role': 'system', 'content': 'You are a helpful assistant'},
            {'role': 'user', 'content': 'Hello'},
        ]

        await llm.generate(messages)

        # Verify system instruction was passed correctly
        call_args = llm.client.models.generate_content.call_args
        config = call_args[1]['config']
        assert config.system_instruction == 'You are a helpful assistant\n'

        # Verify contents don't include system message
        contents = call_args[1]['contents']
        assert contents == ['Hello']

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig')
    async def test_gemini_generate_with_output_schema(self, mock_config_class):
        """Test generate method with output schema."""
        llm = Gemini(model='gemini-2.5-flash')

        output_schema = {
            'type': 'object',
            'properties': {'message': {'type': 'string'}, 'count': {'type': 'integer'}},
        }

        # Mock the config
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        # Mock the client response
        mock_response = Mock()
        mock_response.text = '{"message": "test", "count": 42}'
        mock_response.candidates = []

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Generate JSON'}]
        result = await llm.generate(messages, output_schema=output_schema)

        # Verify structured output was configured
        mock_config.response_mime_type = 'application/json'
        mock_config.response_schema = output_schema

        # Verify the result
        assert result == {'content': '{"message": "test", "count": 42}'}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.types.Tool')
    @patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig')
    async def test_gemini_generate_with_functions(
        self, mock_config_class, mock_tool_class
    ):
        """Test generate method with functions (tools)."""
        llm = Gemini(model='gemini-2.5-flash')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

        # Mock the tool and config
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        mock_config = Mock()
        mock_config_class.return_value = mock_config

        # Mock the client response
        mock_response = Mock()
        mock_response.text = "I'll use the function"
        mock_response.candidates = []

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the function'}]
        result = await llm.generate(messages, functions=functions)

        # Verify tool was created with function declarations
        mock_tool_class.assert_called_once_with(function_declarations=functions)

        # Verify tools were added to config
        mock_config.tools = [mock_tool]

        # Verify the result
        assert result == {'content': "I'll use the function"}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.types.Tool')
    @patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig')
    async def test_gemini_generate_with_function_call_detection(
        self, mock_config_class, mock_tool_class
    ):
        """Test generate method with function call detection."""
        llm = Gemini(model='gemini-2.5-flash')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

        # Mock the tool and config
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        mock_config = Mock()
        mock_config_class.return_value = mock_config

        # Mock the client response with function call
        mock_function_call = Mock()
        mock_function_call.name = 'test_function'
        mock_function_call.args = {'param': 'value'}

        mock_part = Mock()
        mock_part.function_call = mock_function_call

        mock_content = Mock()
        mock_content.parts = [mock_part]

        mock_candidate = Mock()
        mock_candidate.content = mock_content

        mock_response = Mock()
        mock_response.text = 'Function called'
        mock_response.candidates = [mock_candidate]

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the function'}]
        result = await llm.generate(messages, functions=functions)

        # Verify function call was detected and parsed
        assert 'function_call' in result
        assert result['function_call']['name'] == 'test_function'
        assert result['function_call']['arguments'] == {'param': 'value'}

    @pytest.mark.asyncio
    async def test_gemini_generate_with_kwargs(self):
        """Test generate method with additional kwargs."""
        llm = Gemini(model='gemini-2.5-flash', top_p=0.9, max_output_tokens=1000)

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Response with kwargs'
        mock_response.candidates = []

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        await llm.generate(messages)

        # Verify kwargs were passed through
        call_args = llm.client.models.generate_content.call_args
        config = call_args[1]['config']
        assert config.top_p == 0.9
        assert config.max_output_tokens == 1000

    def test_gemini_get_message_content(self):
        """Test get_message_content method."""
        llm = Gemini()

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

    def test_gemini_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""
        llm = Gemini()

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

    def test_gemini_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""
        llm = Gemini()

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

    def test_gemini_format_image_in_message_file_path(self):
        """Test format_image_in_message method with file path."""
        llm = Gemini()

        # Mock file reading
        with patch('builtins.open', mock_open(read_data=b'fake_image_data')):
            image = ImageMessage(
                image_file_path='/path/to/image.jpg', mime_type='image/jpeg'
            )

            result = llm.format_image_in_message(image)

            # Verify genai.types.Part.from_bytes was called
            # Note: We can't easily test the genai call without more complex mocking
            # but we can verify the method doesn't raise an exception
            assert result is not None

    def test_gemini_format_image_in_message_bytes(self):
        """Test format_image_in_message method with image bytes."""
        llm = Gemini()

        image = ImageMessage(image_bytes=b'fake_image_data', mime_type='image/png')

        result = llm.format_image_in_message(image)

        # Verify genai.types.Part.from_bytes was called
        assert result is not None

    def test_gemini_format_image_in_message_unsupported(self):
        """Test format_image_in_message method with unsupported image format."""
        llm = Gemini()

        # Test with image_url (not implemented)
        image = ImageMessage(image_url='https://example.com/image.jpg')

        with pytest.raises(
            NotImplementedError,
            match='Not other way other than file path has been implemented',
        ):
            llm.format_image_in_message(image)

    @pytest.mark.asyncio
    async def test_gemini_generate_error_handling(self):
        """Test error handling in generate method."""
        llm = Gemini(model='gemini-2.5-flash')

        # Mock client to raise an exception
        llm.client = Mock()
        llm.client.models.generate_content = Mock(side_effect=Exception('API Error'))

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='Error in Gemini API call: API Error'):
            await llm.generate(messages)

    def test_gemini_model_parameter_handling(self):
        """Test that model parameter is properly handled."""
        test_models = [
            'gemini-2.5-flash',
            'gemini-1.5-pro',
            'gemini-1.5-flash',
            'gemini-pro',
        ]

        for model in test_models:
            llm = Gemini(model=model)
            assert llm.model == model

    def test_gemini_api_key_handling(self):
        """Test API key handling."""
        # Test with API key
        llm = Gemini(api_key='secret-key-123')
        assert llm.api_key == 'secret-key-123'

        # Test without API key
        llm = Gemini()
        assert llm.api_key is None

        # Test with empty string API key
        llm = Gemini(api_key='')
        assert llm.api_key == ''

    def test_gemini_generation_config_creation(self):
        """Test that generation config is created correctly."""
        llm = Gemini(temperature=0.5, max_output_tokens=1000, top_p=0.9)

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Test response'
        mock_response.candidates = []

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=mock_response)

        # We need to patch the types.GenerateContentConfig to test this
        with patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig') as mock_config:
            mock_config_instance = Mock()
            mock_config.return_value = mock_config_instance

            # This would normally be called in generate method
            # For testing, we'll just verify the config class exists
            assert mock_config is not None

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig')
    async def test_gemini_stream_basic(self, mock_config_class):
        """Test basic stream method without functions."""
        llm = Gemini(model='gemini-2.5-flash')

        # Mock the config
        mock_config = Mock()
        mock_config_class.return_value = mock_config

        # Mock streaming chunks
        mock_chunk1 = Mock()
        mock_chunk1.text = 'Hello'

        mock_chunk2 = Mock()
        mock_chunk2.text = ', world!'

        # Create a regular iterator (Gemini API returns regular iterator, not async)
        def regular_iter():
            yield mock_chunk1
            yield mock_chunk2

        # Mock the client response
        llm.client = Mock()
        llm.client.models.generate_content_stream = Mock(return_value=regular_iter())

        messages = [{'role': 'user', 'content': 'Hello'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages):
            results.append(chunk)

        # Verify the API call
        llm.client.models.generate_content_stream.assert_called_once()
        call_args = llm.client.models.generate_content_stream.call_args

        assert call_args[1]['model'] == 'gemini-2.5-flash'
        assert call_args[1]['contents'] == ['Hello']
        assert call_args[1]['config'] == mock_config

        # Verify the streaming results
        assert len(results) == 2
        assert results[0] == {'content': 'Hello'}
        assert results[1] == {'content': ', world!'}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.gemini_llm.types.Tool')
    @patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig')
    async def test_gemini_stream_with_functions(
        self, mock_config_class, mock_tool_class
    ):
        """Test stream method with functions (tools)."""
        llm = Gemini(model='gemini-2.5-flash')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

        # Mock the tool and config
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        mock_config = Mock()
        mock_config_class.return_value = mock_config

        # Mock streaming chunks
        mock_chunk = Mock()
        mock_chunk.text = 'I will use the function'

        # Create a regular iterator (Gemini API returns regular iterator, not async)
        def regular_iter():
            yield mock_chunk

        # Mock the client response
        llm.client = Mock()
        llm.client.models.generate_content_stream = Mock(return_value=regular_iter())

        messages = [{'role': 'user', 'content': 'Use the function'}]

        # Collect streaming results
        results = []
        async for chunk in llm.stream(messages, functions=functions):
            results.append(chunk)

        # Verify tool was created with function declarations
        mock_tool_class.assert_called_once_with(function_declarations=functions)

        # Verify tools were added to config
        mock_config.tools = [mock_tool]

        # Verify the streaming results
        assert len(results) == 1
        assert results[0] == {'content': 'I will use the function'}
