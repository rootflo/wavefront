#!/usr/bin/env python3
"""
Pytest tests for the BaseLLM abstract class and ImageMessageContent dataclass.
"""

import sys
import os
import pytest
from unittest.mock import Mock

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models import ImageMessageContent


class MockLLM(BaseLLM):
    """Mock LLM implementation for testing BaseLLM functionality"""

    async def generate(self, messages, functions=None):
        return {'content': 'Mock response'}

    async def get_function_call(self, response):
        if hasattr(response, 'function_call') and response.function_call:
            return {
                'name': response.function_call.name,
                'arguments': response.function_call.arguments,
            }
        elif isinstance(response, dict) and 'function_call' in response:
            return {
                'name': response['function_call']['name'],
                'arguments': response['function_call']['arguments'],
            }
        return None

    async def stream(self, messages, functions=None):
        async def generator():
            yield {'response': self.response_text}

        return generator()

    def get_message_content(self, response):
        if isinstance(response, dict):
            return response.get('content', '')
        return str(response)

    def format_tool_for_llm(self, tool):
        return {
            'name': tool.name,
            'description': tool.description,
            'parameters': {'type': 'object', 'properties': {}},
        }

    def format_tools_for_llm(self, tools):
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image):
        return f'image:{image.mime_type}'


class TestImageMessageContent:
    """Test class for ImageMessageContent dataclass."""

    def test_image_message_defaults(self):
        """Test ImageMessageContent with no parameters."""
        img = ImageMessageContent()
        assert img.url is None
        assert img.base64 is None
        assert img.mime_type is None


class TestBaseLLM:
    """Test class for BaseLLM abstract class functionality."""

    def test_base_llm_initialization(self):
        """Test BaseLLM initialization with different parameters."""
        # Test with minimal parameters
        llm = MockLLM(model='test-model')
        assert llm.model == 'test-model'
        assert llm.api_key is None
        assert llm.temperature == 0.7
        assert llm.kwargs == {}

        # Test with all parameters
        llm = MockLLM(
            model='test-model-2',
            api_key='test-key',
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
        )
        assert llm.model == 'test-model-2'
        assert llm.api_key == 'test-key'
        assert llm.temperature == 0.5
        assert llm.kwargs == {'max_tokens': 100, 'top_p': 0.9}

    def test_base_llm_temperature_validation(self):
        """Test temperature parameter handling."""
        # Test default temperature
        llm = MockLLM(model='test-model')
        assert llm.temperature == 0.7

        # Test custom temperature
        llm = MockLLM(model='test-model', temperature=0.0)
        assert llm.temperature == 0.0

        # Test high temperature
        llm = MockLLM(model='test-model', temperature=1.0)
        assert llm.temperature == 1.0

        # Test temperature in kwargs
        llm = MockLLM(model='test-model', temperature=0.3, custom_temp=0.8)
        assert llm.temperature == 0.3
        assert llm.kwargs['custom_temp'] == 0.8

    def test_base_llm_kwargs_storage(self):
        """Test that additional kwargs are properly stored."""
        llm = MockLLM(
            model='test-model',
            max_tokens=1000,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1,
        )

        assert 'max_tokens' in llm.kwargs
        assert 'top_p' in llm.kwargs
        assert 'frequency_penalty' in llm.kwargs
        assert 'presence_penalty' in llm.kwargs
        assert llm.kwargs['max_tokens'] == 1000
        assert llm.kwargs['top_p'] == 0.9

    @pytest.mark.asyncio
    async def test_base_llm_get_function_call(self):
        """Test get_function_call method with different response formats."""
        llm = MockLLM(model='test-model')

        # Test with response object that has function_call attribute
        mock_response = Mock()
        mock_response.function_call.name = 'test_function'
        mock_response.function_call.arguments = '{"param": "value"}'

        result = await llm.get_function_call(mock_response)
        assert result == {'name': 'test_function', 'arguments': '{"param": "value"}'}

        # Test with dict response
        dict_response = {
            'function_call': {
                'name': 'test_function_2',
                'arguments': '{"param2": "value2"}',
            }
        }

        result = await llm.get_function_call(dict_response)
        assert result == {
            'name': 'test_function_2',
            'arguments': '{"param2": "value2"}',
        }

        # Test with response that has no function_call
        no_function_response = {'content': 'No function call here'}
        result = await llm.get_function_call(no_function_response)
        assert result is None

        # Test with response that has function_call but it's None
        none_function_response = Mock()
        none_function_response.function_call = None

        result = await llm.get_function_call(none_function_response)
        assert result is None

    def test_base_llm_abstract_methods(self):
        """Test that abstract methods are properly defined."""
        # This should not raise an error since MockLLM implements all abstract methods
        llm = MockLLM(model='test-model')

        # Verify all required methods exist
        assert hasattr(llm, 'generate')
        assert hasattr(llm, 'get_message_content')
        assert hasattr(llm, 'format_tool_for_llm')
        assert hasattr(llm, 'format_tools_for_llm')
        assert hasattr(llm, 'format_image_in_message')

        # Verify they are callable
        assert callable(llm.generate)
        assert callable(llm.get_message_content)
        assert callable(llm.format_tool_for_llm)
        assert callable(llm.format_tools_for_llm)
        assert callable(llm.format_image_in_message)

    def test_base_llm_cannot_instantiate_abstract(self):
        """Test that BaseLLM cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseLLM(model='test-model')

    def test_base_llm_model_validation(self):
        """Test that model parameter is properly set."""
        test_models = ['gpt-4', 'claude-3', 'gemini-pro', 'llama2']

        for model in test_models:
            llm = MockLLM(model=model)
            assert llm.model == model

    def test_base_llm_api_key_handling(self):
        """Test API key handling."""
        # Test with API key
        llm = MockLLM(model='test-model', api_key='secret-key-123')
        assert llm.api_key == 'secret-key-123'

        # Test without API key
        llm = MockLLM(model='test-model')
        assert llm.api_key is None

        # Test with empty string API key
        llm = MockLLM(model='test-model', api_key='')
        assert llm.api_key == ''
