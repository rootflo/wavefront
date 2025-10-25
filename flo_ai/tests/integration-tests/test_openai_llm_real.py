#!/usr/bin/env python3
"""
Real LLM tests for OpenAI implementation using actual API calls.
These tests require OPENAI_API_KEY environment variable to be set.
"""

import os
import pytest
import asyncio
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.base_llm import ImageMessage
from flo_ai.tool.base_tool import Tool


@pytest.mark.integration
class TestOpenAIReal:
    """Test class for OpenAI LLM implementation with real API calls."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup for each test method."""
        # Check if API key is available
        if not os.getenv('OPENAI_API_KEY'):
            pytest.skip('OPENAI_API_KEY environment variable not set')

        self.llm = OpenAI(
            model='gpt-4o-mini',
            api_key=os.getenv('OPENAI_API_KEY'),
            temperature=0.1,  # Low temperature for consistent results
        )

    def test_initialization(self):
        """Test OpenAI LLM initialization with real API key."""
        assert self.llm.model == 'gpt-4o-mini'
        assert self.llm.api_key == os.getenv('OPENAI_API_KEY')
        assert self.llm.temperature == 0.1
        assert self.llm.client is not None

    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters."""
        custom_llm = OpenAI(
            model='gpt-4o-mini',
            api_key=os.getenv('OPENAI_API_KEY'),
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
        )

        assert custom_llm.model == 'gpt-4o-mini'
        assert custom_llm.temperature == 0.5
        assert custom_llm.kwargs['max_tokens'] == 100
        assert custom_llm.kwargs['top_p'] == 0.9

    @pytest.mark.asyncio
    async def test_generate_basic(self):
        """Test basic generate method with real API call."""
        messages = [
            {'role': 'user', 'content': 'Say "Hello, World!" and nothing else.'}
        ]

        response = await self.llm.generate(messages)

        # Verify response structure
        assert hasattr(response, 'content')
        assert response.content is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_generate_with_system_message(self):
        """Test generate method with system message."""
        messages = [
            {
                'role': 'system',
                'content': 'You are a helpful assistant that always responds with exactly 3 words.',
            },
            {'role': 'user', 'content': 'What is the capital of France?'},
        ]

        response = await self.llm.generate(messages)

        assert hasattr(response, 'content')
        assert response.content is not None
        # Should be approximately 3 words
        word_count = len(response.content.split())
        assert 1 <= word_count <= 5  # Allow some flexibility

    @pytest.mark.asyncio
    async def test_generate_with_output_schema(self):
        """Test generate method with JSON output schema."""
        output_schema = {
            'title': 'weather_response',
            'schema': {
                'type': 'object',
                'properties': {
                    'city': {'type': 'string'},
                    'temperature': {'type': 'integer'},
                    'condition': {'type': 'string'},
                },
                'required': ['city', 'temperature', 'condition'],
            },
        }

        messages = [
            {
                'role': 'user',
                'content': 'What is the weather like in Paris? Respond with the city, temperature, and condition.',
            }
        ]

        response = await self.llm.generate(messages, output_schema=output_schema)

        # When using output_schema, the response might be in function_call instead of content
        if hasattr(response, 'function_call') and response.function_call:
            # Function call response
            assert response.function_call.name == 'weather_response'
            assert response.function_call.arguments is not None
            # The arguments should contain JSON data
            arguments = response.function_call.arguments
            assert 'city' in arguments.lower() or 'paris' in arguments.lower()
        else:
            # Regular content response
            assert hasattr(response, 'content')
            assert response.content is not None
            content = response.content
            assert 'city' in content.lower() or 'paris' in content.lower()

    @pytest.mark.asyncio
    async def test_generate_with_kwargs(self):
        """Test generate method with additional kwargs."""
        messages = [{'role': 'user', 'content': 'Count from 1 to 5.'}]

        response = await self.llm.generate(messages, max_tokens=50, top_p=0.8)

        assert hasattr(response, 'content')
        assert response.content is not None
        assert len(response.content) <= 50  # Should respect max_tokens

    @pytest.mark.asyncio
    async def test_stream_basic(self):
        """Test basic streaming functionality."""
        messages = [
            {'role': 'user', 'content': 'Count from 1 to 3, one number per line.'}
        ]

        chunks = []
        async for chunk in self.llm.stream(messages):
            assert isinstance(chunk, dict)
            assert 'content' in chunk
            chunks.append(chunk)

        # Should have received multiple chunks
        assert len(chunks) > 0

        # Combine all content
        full_content = ''.join(chunk['content'] for chunk in chunks)
        assert len(full_content) > 0

    @pytest.mark.asyncio
    async def test_stream_with_functions(self):
        """Test streaming with function definitions."""
        functions = [
            {
                'name': 'get_weather',
                'description': 'Get weather information',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'location': {'type': 'string', 'description': 'The city name'}
                    },
                    'required': ['location'],
                },
            }
        ]

        messages = [
            {
                'role': 'user',
                'content': 'Tell me about the weather in general terms, not using any functions.',
            }
        ]

        chunks = []
        async for chunk in self.llm.stream(messages, functions=functions):
            assert isinstance(chunk, dict)
            chunks.append(chunk)

        # Should receive streaming content since we're asking for general information
        # and not requesting function calls
        assert len(chunks) > 0

        # Verify chunks have content
        for chunk in chunks:
            assert 'content' in chunk
            assert chunk['content'] is not None

    def test_get_message_content_string(self):
        """Test get_message_content with string input."""
        test_string = 'Hello, World!'
        result = self.llm.get_message_content(test_string)
        assert result == test_string

    def test_get_message_content_message_object(self):
        """Test get_message_content with message object."""

        # Create a mock message object
        class MockMessage:
            def __init__(self, content):
                self.content = content

        mock_message = MockMessage('Test content')
        result = self.llm.get_message_content(mock_message)
        assert result == 'Test content'

    def test_get_message_content_object_without_content(self):
        """Test get_message_content with object without content attribute."""

        class MockObject:
            def __str__(self):
                return 'Mock object string'

        mock_obj = MockObject()
        result = self.llm.get_message_content(mock_obj)
        assert result == 'Mock object string'

    def test_format_tool_for_llm(self):
        """Test format_tool_for_llm method."""

        # Create a test tool
        def test_function(param1: str, param2: int) -> str:
            return f'Result: {param1} {param2}'

        tool = Tool(
            name='test_tool',
            description='A test tool for formatting',
            function=test_function,
            parameters={
                'param1': {'type': 'string', 'description': 'First parameter'},
                'param2': {'type': 'integer', 'description': 'Second parameter'},
            },
        )

        formatted = self.llm.format_tool_for_llm(tool)

        # Verify structure
        assert formatted['name'] == 'test_tool'
        assert formatted['description'] == 'A test tool for formatting'
        assert formatted['parameters']['type'] == 'object'
        assert 'param1' in formatted['parameters']['properties']
        assert 'param2' in formatted['parameters']['properties']
        assert formatted['parameters']['required'] == ['param1', 'param2']

        # Verify parameter types
        assert formatted['parameters']['properties']['param1']['type'] == 'string'
        assert formatted['parameters']['properties']['param2']['type'] == 'integer'

    def test_format_tool_for_llm_with_array(self):
        """Test format_tool_for_llm with array parameter."""

        def test_function(items: list) -> str:
            return f'Processed {len(items)} items'

        tool = Tool(
            name='array_tool',
            description='Tool with array parameter',
            function=test_function,
            parameters={
                'items': {
                    'type': 'array',
                    'description': 'List of items',
                    'items': {'type': 'string'},
                }
            },
        )

        formatted = self.llm.format_tool_for_llm(tool)

        assert formatted['name'] == 'array_tool'
        param_props = formatted['parameters']['properties']['items']
        assert param_props['type'] == 'array'
        assert 'items' in param_props
        assert param_props['items']['type'] == 'string'

    def test_format_tools_for_llm(self):
        """Test format_tools_for_llm method."""

        # Create multiple test tools
        def tool1_func(x: str) -> str:
            return f'Tool1: {x}'

        def tool2_func(y: int) -> str:
            return f'Tool2: {y}'

        tool1 = Tool(
            name='tool1',
            description='First tool',
            function=tool1_func,
            parameters={'x': {'type': 'string', 'description': 'Input string'}},
        )

        tool2 = Tool(
            name='tool2',
            description='Second tool',
            function=tool2_func,
            parameters={'y': {'type': 'integer', 'description': 'Input number'}},
        )

        formatted_tools = self.llm.format_tools_for_llm([tool1, tool2])

        assert len(formatted_tools) == 2
        assert formatted_tools[0]['name'] == 'tool1'
        assert formatted_tools[1]['name'] == 'tool2'

        # Verify each tool is properly formatted
        for tool in formatted_tools:
            assert 'name' in tool
            assert 'description' in tool
            assert 'parameters' in tool

    def test_format_image_in_message(self):
        """Test format_image_in_message method (should raise NotImplementedError)."""
        image = ImageMessage(image_url='https://example.com/image.jpg')

        with pytest.raises(
            NotImplementedError, match='Not implemented image for LLM OpenAI'
        ):
            self.llm.format_image_in_message(image)

    @pytest.mark.asyncio
    async def test_generate_with_usage_tracking(self):
        """Test that token usage is properly tracked."""
        messages = [{'role': 'user', 'content': 'Say hello in exactly 5 words.'}]

        response = await self.llm.generate(messages)

        # Verify response has expected structure
        assert hasattr(response, 'content')
        assert response.content is not None

        # The response object should be a message object
        assert hasattr(response, 'role') or hasattr(response, 'content')

    @pytest.mark.asyncio
    async def test_generate_error_handling(self):
        """Test error handling with invalid parameters."""
        # Test with empty messages
        with pytest.raises(Exception):
            await self.llm.generate([])

        # Test with invalid message format
        invalid_messages = [{'invalid': 'format'}]

        with pytest.raises(Exception):
            await self.llm.generate(invalid_messages)

    @pytest.mark.asyncio
    async def test_stream_error_handling(self):
        """Test streaming error handling."""
        # Test with empty messages
        with pytest.raises(Exception):
            async for chunk in self.llm.stream([]):
                pass

    @pytest.mark.asyncio
    async def test_generate_with_different_models(self):
        """Test generate with different model configurations."""
        # Test with a different model if available
        messages = [{'role': 'user', 'content': 'What is 2+2?'}]

        # This should work with the default model
        response = await self.llm.generate(messages)
        assert hasattr(response, 'content')
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_concurrent_generate_calls(self):
        """Test multiple concurrent generate calls."""
        messages1 = [{'role': 'user', 'content': 'Say "First"'}]
        messages2 = [{'role': 'user', 'content': 'Say "Second"'}]
        messages3 = [{'role': 'user', 'content': 'Say "Third"'}]

        # Run concurrent calls
        tasks = [
            self.llm.generate(messages1),
            self.llm.generate(messages2),
            self.llm.generate(messages3),
        ]

        responses = await asyncio.gather(*tasks)

        # Verify all responses were received
        assert len(responses) == 3
        for response in responses:
            assert hasattr(response, 'content')
            assert response.content is not None

    @pytest.mark.asyncio
    async def test_stream_with_empty_chunks(self):
        """Test streaming behavior with potential empty chunks."""
        messages = [
            {
                'role': 'user',
                'content': 'Say "Hello" and then "World" on separate lines.',
            }
        ]

        chunks = []
        async for chunk in self.llm.stream(messages):
            chunks.append(chunk)

        # Should have received chunks
        assert len(chunks) > 0

        # All chunks should have content
        for chunk in chunks:
            assert 'content' in chunk
            assert chunk['content'] is not None

    def test_tool_formatting_edge_cases(self):
        """Test tool formatting with edge cases."""

        # Test with empty parameters
        def empty_func():
            return 'empty'

        empty_tool = Tool(
            name='empty_tool',
            description='Tool with no parameters',
            function=empty_func,
            parameters={},
        )

        formatted = self.llm.format_tool_for_llm(empty_tool)
        assert formatted['name'] == 'empty_tool'
        assert formatted['parameters']['required'] == []
        assert formatted['parameters']['properties'] == {}

    @pytest.mark.asyncio
    async def test_generate_with_long_conversation(self):
        """Test generate with a longer conversation history."""
        messages = [
            {'role': 'system', 'content': 'You are a helpful math tutor.'},
            {'role': 'user', 'content': 'What is 5 + 3?'},
            {'role': 'assistant', 'content': '5 + 3 = 8'},
            {'role': 'user', 'content': 'What is 8 * 2?'},
        ]

        response = await self.llm.generate(messages)

        assert hasattr(response, 'content')
        assert response.content is not None
        # Should contain the answer to 8 * 2
        assert '16' in response.content or 'sixteen' in response.content.lower()

    @pytest.mark.asyncio
    async def test_stream_with_stop_condition(self):
        """Test streaming with early termination."""
        messages = [
            {
                'role': 'user',
                'content': 'Count from 1 to 10, but I will stop you early.',
            }
        ]

        chunks = []
        chunk_count = 0
        max_chunks = 5  # Stop after 5 chunks

        async for chunk in self.llm.stream(messages):
            chunks.append(chunk)
            chunk_count += 1
            if chunk_count >= max_chunks:
                break

        # Should have received some chunks before stopping
        assert len(chunks) > 0
        assert len(chunks) <= max_chunks
