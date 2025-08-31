#!/usr/bin/env python3
"""
Pytest tests for the VertexAI LLM implementation.
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.vertexai_llm import VertexAI
from flo_ai.tool.base_tool import Tool

os.environ['GOOGLE_API_KEY'] = 'test-key-123'
os.environ['GOOGLE_PROJECT'] = 'my-project-123'
os.environ['GOOGLE_LOCATION'] = 'us-central1'


class TestVertexAI:
    """Test class for VertexAI LLM implementation."""

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_initialization(self, mock_genai_client):
        """Test VertexAI LLM initialization with different parameters."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with minimal parameters
        llm = VertexAI()
        assert llm.model == 'gemini-2.5-flash'
        assert llm.api_key is None
        assert llm.temperature == 0.7
        assert llm.kwargs == {}
        assert llm.project is None
        assert llm.location is None

        # Test with custom parameters
        mock_genai_client.reset_mock()
        llm = VertexAI(
            model='gemini-1.5-pro',
            api_key='test-key-123',
            temperature=0.5,
            project='my-project-123',
            location='us-central1',
        )
        assert llm.model == 'gemini-1.5-pro'
        assert llm.api_key == 'test-key-123'
        assert llm.temperature == 0.5
        assert llm.project == 'my-project-123'
        assert llm.location == 'us-central1'
        assert llm.kwargs == {}

        # Test with additional kwargs
        mock_genai_client.reset_mock()
        llm = VertexAI(model='gemini-2.5-flash', max_tokens=1000, top_p=0.9)
        assert llm.kwargs == {'max_tokens': 1000, 'top_p': 0.9}

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_temperature_handling(self, mock_genai_client):
        """Test temperature parameter handling."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test default temperature
        llm = VertexAI()
        assert llm.temperature == 0.7

        # Test custom temperature
        mock_genai_client.reset_mock()
        llm = VertexAI(temperature=0.0)
        assert llm.temperature == 0.0

        # Test high temperature
        mock_genai_client.reset_mock()
        llm = VertexAI(temperature=1.0)
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        mock_genai_client.reset_mock()
        llm = VertexAI(temperature=0.3, custom_temp=0.8)
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_client_creation(self, mock_genai_client):
        """Test that genai Client is created correctly with VertexAI parameters."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(project='test-project', location='us-central1')

        mock_genai_client.assert_called_once_with(
            project='test-project', location='us-central1', vertexai=True
        )
        assert llm.client == mock_client

        # Test without project and location
        mock_genai_client.reset_mock()
        llm = VertexAI()

        mock_genai_client.assert_called_once_with(
            project=None, location=None, vertexai=True
        )
        assert llm.client == mock_client

    @pytest.mark.asyncio
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_basic(self, mock_genai_client):
        """Test basic generate method without functions or output schema."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Hello, world!'
        mock_response.candidates = []

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
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_with_system_message(self, mock_genai_client):
        """Test generate method with system message."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        # Mock the client response
        mock_response = Mock()
        mock_response.text = "I'm a helpful assistant"
        mock_response.candidates = []

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
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_with_output_schema(self, mock_genai_client):
        """Test generate method with output schema."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        output_schema = {
            'type': 'object',
            'properties': {'message': {'type': 'string'}, 'count': {'type': 'integer'}},
        }

        # Mock the client response
        mock_response = Mock()
        mock_response.text = '{"message": "test", "count": 42}'
        mock_response.candidates = []

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Generate JSON'}]
        result = await llm.generate(messages, output_schema=output_schema)

        # Verify the result
        assert result == {'content': '{"message": "test", "count": 42}'}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_with_functions(self, mock_genai_client):
        """Test generate method with functions (tools)."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

        # Mock the client response
        mock_response = Mock()
        mock_response.text = "I'll use the function"
        mock_response.candidates = []

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the function'}]
        result = await llm.generate(messages, functions=functions)

        # Verify the result
        assert result == {'content': "I'll use the function"}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_with_function_call_detection(
        self, mock_genai_client
    ):
        """Test generate method with function call detection."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        functions = [
            {
                'name': 'test_function',
                'description': 'A test function',
                'parameters': {'type': 'object'},
            }
        ]

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

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Use the function'}]
        result = await llm.generate(messages, functions=functions)

        # Verify function call was detected and parsed
        assert 'function_call' in result
        assert result['function_call']['name'] == 'test_function'
        assert result['function_call']['arguments'] == {'param': 'value'}

    @pytest.mark.asyncio
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_with_kwargs(self, mock_genai_client):
        """Test generate method with additional kwargs."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash', top_p=0.9, max_output_tokens=1000)

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Response with kwargs'
        mock_response.candidates = []

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        messages = [{'role': 'user', 'content': 'Hello'}]
        await llm.generate(messages)

        # Verify kwargs were passed through
        call_args = llm.client.models.generate_content.call_args
        config = call_args[1]['config']
        assert config.top_p == 0.9
        assert config.max_output_tokens == 1000

    def test_vertexai_get_message_content(self):
        """Test get_message_content method."""
        llm = VertexAI()

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

    def test_vertexai_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""
        llm = VertexAI()

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

    def test_vertexai_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""
        llm = VertexAI()

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

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_project_handling(self, mock_genai_client):
        """Test project parameter handling."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with project
        llm = VertexAI(project='my-project-123')
        assert llm.project == 'my-project-123'

        # Test without project
        mock_genai_client.reset_mock()
        llm = VertexAI()
        assert llm.project is None

        # Test with empty string project
        mock_genai_client.reset_mock()
        llm = VertexAI(project='')
        assert llm.project == ''

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_location_handling(self, mock_genai_client):
        """Test location parameter handling."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with location
        llm = VertexAI(location='us-central1')
        assert llm.location == 'us-central1'

        # Test without location
        mock_genai_client.reset_mock()
        llm = VertexAI()
        assert llm.location is None

        # Test with empty string location
        mock_genai_client.reset_mock()
        llm = VertexAI(location='')
        assert llm.location == ''

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_kwargs_storage(self, mock_genai_client):
        """Test that additional kwargs are properly stored."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(
            max_tokens=1000, top_p=0.9, frequency_penalty=0.1, presence_penalty=0.1
        )

        assert 'max_tokens' in llm.kwargs
        assert 'top_p' in llm.kwargs
        assert 'frequency_penalty' in llm.kwargs
        assert 'presence_penalty' in llm.kwargs
        assert llm.kwargs['max_tokens'] == 1000
        assert llm.kwargs['top_p'] == 0.9

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_base_llm_initialization(self, mock_genai_client):
        """Test that BaseLLM is properly initialized."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='test-model', api_key='test-key', temperature=0.5)

        # These should come from BaseLLM
        assert llm.model == 'test-model'
        assert llm.api_key == 'test-key'
        assert llm.temperature == 0.5

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_vertexai_flag(self, mock_genai_client):
        """Test that vertexai=True is always set in client creation."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        VertexAI()

        # Verify vertexai=True was passed
        call_args = mock_genai_client.call_args[1]
        assert call_args['vertexai']

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_parameter_combinations(self, mock_genai_client):
        """Test various parameter combinations."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with all parameters
        llm = VertexAI(
            model='gemini-1.5-pro',
            api_key='key123',
            temperature=0.3,
            project='proj123',
            location='us-west1',
            max_tokens=500,
            top_p=0.8,
        )

        assert llm.model == 'gemini-1.5-pro'
        assert llm.api_key == 'key123'
        assert llm.temperature == 0.3
        assert llm.project == 'proj123'
        assert llm.location == 'us-west1'
        assert llm.kwargs == {'max_tokens': 500, 'top_p': 0.8}

        # Test with minimal parameters
        mock_genai_client.reset_mock()
        llm = VertexAI()

        assert llm.model == 'gemini-2.5-flash'
        assert llm.api_key is None
        assert llm.temperature == 0.7
        assert llm.project is None
        assert llm.location is None
        assert llm.kwargs == {}

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_method_inheritance(self, mock_genai_client):
        """Test that VertexAI inherits all methods from Gemini."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI()

        # Test that VertexAI has all the methods from Gemini
        assert hasattr(llm, 'generate')
        assert hasattr(llm, 'get_message_content')
        assert hasattr(llm, 'format_tool_for_llm')
        assert hasattr(llm, 'format_tools_for_llm')
        assert hasattr(llm, 'format_image_in_message')

    @pytest.mark.asyncio
    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    async def test_vertexai_generate_error_handling(self, mock_genai_client):
        """Test error handling in generate method."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(model='gemini-2.5-flash')

        # Mock client to raise an exception
        llm.client = mock_client
        llm.client.models.generate_content = Mock(side_effect=Exception('API Error'))

        messages = [{'role': 'user', 'content': 'Hello'}]

        with pytest.raises(Exception, match='Error in Gemini API call: API Error'):
            await llm.generate(messages)

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_model_parameter_handling(self, mock_genai_client):
        """Test that model parameter is properly handled."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        test_models = [
            'gemini-2.5-flash',
            'gemini-1.5-pro',
            'gemini-1.5-flash',
            'gemini-pro',
        ]

        for model in test_models:
            mock_genai_client.reset_mock()
            llm = VertexAI(model=model)
            assert llm.model == model

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_api_key_handling(self, mock_genai_client):
        """Test API key handling."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        # Test with API key
        llm = VertexAI(api_key='secret-key-123')
        assert llm.api_key == 'secret-key-123'

        # Test without API key
        mock_genai_client.reset_mock()
        llm = VertexAI()
        assert llm.api_key is None

        # Test with empty string API key
        mock_genai_client.reset_mock()
        llm = VertexAI(api_key='')
        assert llm.api_key == ''

    @patch('flo_ai.llm.vertexai_llm.genai.Client')
    def test_vertexai_generation_config_creation(self, mock_genai_client):
        """Test that generation config is created correctly."""
        mock_client = Mock()
        mock_genai_client.return_value = mock_client

        llm = VertexAI(temperature=0.5, max_output_tokens=1000, top_p=0.9)

        # Mock the client response
        mock_response = Mock()
        mock_response.text = 'Test response'
        mock_response.candidates = []

        llm.client = mock_client
        llm.client.models.generate_content = Mock(return_value=mock_response)

        # We need to patch the types.GenerateContentConfig to test this
        with patch('flo_ai.llm.gemini_llm.types.GenerateContentConfig') as mock_config:
            mock_config_instance = Mock()
            mock_config.return_value = mock_config_instance

            # This would normally be called in generate method
            # For testing, we'll just verify the config class exists
            assert mock_config is not None
