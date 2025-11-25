"""
Test cases for LLM-powered routers in Arium workflows.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from typing import Literal

from flo_ai.arium.llm_router import (
    SmartRouter,
    TaskClassifierRouter,
    ConversationAnalysisRouter,
    create_llm_router,
    llm_router,
)
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models import UserMessage


class MockLLM(BaseLLM):
    """Mock LLM for testing"""

    def __init__(self, response_text: str = 'researcher'):
        super().__init__(model='mock')
        self.response_text = response_text
        self.call_count = 0

    async def generate(self, messages, **kwargs):
        self.call_count += 1
        return {'response': self.response_text}

    async def stream(self, messages, functions=None):
        async def generator():
            yield {'response': self.response_text}

        return generator()

    def get_message_content(self, response):
        return response.get('response', 'researcher')

    def format_tool_for_llm(self, tool):
        """Mock implementation for tool formatting"""
        return {'name': tool.name, 'description': 'mock tool'}

    def format_tools_for_llm(self, tools):
        """Mock implementation for tools formatting"""
        return [self.format_tool_for_llm(tool) for tool in tools]

    def format_image_in_message(self, image):
        """Mock implementation for image formatting"""
        return 'mock_image_content'


@pytest.fixture
def mock_memory():
    """Create a mock memory with sample conversation"""
    memory = MessageMemory()
    memory.add(
        MessageMemoryItem(
            node='researcher',
            result=UserMessage('I need to research market trends for renewable energy'),
        )
    )
    memory.add(
        MessageMemoryItem(
            node='analyst',
            result=UserMessage('Please analyze the data and provide insights'),
        )
    )
    return memory


class TestSmartRouter:
    """Test SmartRouter functionality"""

    def test_initialization(self):
        """Test SmartRouter initialization"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('researcher')
        router = SmartRouter(routing_options, llm=mock_llm)

        assert router.get_routing_options() == routing_options
        assert router.llm == mock_llm

    @pytest.mark.asyncio
    async def test_route_decision(self, mock_memory):
        """Test routing decision making"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('researcher')
        router = SmartRouter(routing_options, llm=mock_llm)

        result = await router.route(mock_memory)

        assert result == 'researcher'
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_response(self, mock_memory):
        """Test fallback when LLM returns invalid response"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('invalid_response')
        router = SmartRouter(
            routing_options, llm=mock_llm, max_retries=1, fallback_strategy='first'
        )

        result = await router.route(mock_memory)

        assert result == 'researcher'  # First option as fallback
        assert mock_llm.call_count == 1  # Should retry once

    def test_get_routing_prompt(self, mock_memory):
        """Test routing prompt generation"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('researcher')
        router = SmartRouter(routing_options, llm=mock_llm)
        prompt = router.get_routing_prompt(mock_memory, routing_options)

        assert 'researcher' in prompt
        assert 'analyst' in prompt
        assert 'Research tasks' in prompt
        assert 'Analysis tasks' in prompt


class TestTaskClassifierRouter:
    """Test TaskClassifierRouter functionality"""

    def test_initialization(self):
        """Test TaskClassifierRouter initialization"""
        task_categories = {
            'math': {
                'description': 'Math tasks',
                'keywords': ['calculate', 'math'],
                'examples': ['Calculate sum'],
            }
        }

        mock_llm = MockLLM('math')
        router = TaskClassifierRouter(task_categories, llm=mock_llm)

        assert router.task_categories == task_categories
        assert router.get_routing_options() == {'math': 'Math tasks'}

    @pytest.mark.asyncio
    async def test_route_with_keywords(self, mock_memory):
        """Test routing based on keywords"""
        task_categories = {
            'math': {
                'description': 'Math tasks',
                'keywords': ['calculate', 'math'],
                'examples': ['Calculate sum'],
            },
            'research': {
                'description': 'Research tasks',
                'keywords': ['research', 'find'],
                'examples': ['Find information'],
            },
        }

        mock_llm = MockLLM('research')
        router = TaskClassifierRouter(task_categories, llm=mock_llm)

        result = await router.route(mock_memory)

        assert result == 'research'


class TestConversationAnalysisRouter:
    """Test ConversationAnalysisRouter functionality"""

    def test_initialization(self):
        """Test ConversationAnalysisRouter initialization"""
        routing_logic = {'planner': 'Plan tasks', 'executor': 'Execute tasks'}

        mock_llm = MockLLM('planner')
        router = ConversationAnalysisRouter(
            routing_logic, analysis_depth=2, llm=mock_llm
        )

        assert router.routing_logic == routing_logic
        assert router.analysis_depth == 2

    @pytest.mark.asyncio
    async def test_route_with_conversation_analysis(self, mock_memory):
        """Test routing based on conversation analysis"""
        routing_logic = {'planner': 'Plan tasks', 'executor': 'Execute tasks'}

        mock_llm = MockLLM('executor')
        router = ConversationAnalysisRouter(routing_logic, llm=mock_llm)

        result = await router.route(mock_memory)

        assert result == 'executor'


class TestFactoryFunction:
    """Test create_llm_router factory function"""

    def test_create_smart_router(self):
        """Test creating SmartRouter via factory"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('researcher')
        router_fn = create_llm_router(
            'smart', routing_options=routing_options, llm=mock_llm
        )

        assert callable(router_fn)
        assert hasattr(router_fn, '__annotations__')

    def test_create_task_classifier_router(self):
        """Test creating TaskClassifierRouter via factory"""
        task_categories = {
            'math': {
                'description': 'Math tasks',
                'keywords': ['calculate'],
                'examples': ['Calculate sum'],
            }
        }

        mock_llm = MockLLM('math')
        router_fn = create_llm_router(
            'task_classifier', task_categories=task_categories, llm=mock_llm
        )

        assert callable(router_fn)

    def test_create_conversation_analysis_router(self):
        """Test creating ConversationAnalysisRouter via factory"""
        routing_logic = {'planner': 'Plan tasks', 'executor': 'Execute tasks'}

        mock_llm = MockLLM('planner')
        router_fn = create_llm_router(
            'conversation_analysis', routing_logic=routing_logic, llm=mock_llm
        )

        assert callable(router_fn)

    def test_invalid_router_type(self):
        """Test error on invalid router type"""
        with pytest.raises(ValueError, match='Unknown router type'):
            create_llm_router('invalid_type')


class TestDecorator:
    """Test @llm_router decorator"""

    def test_decorator_creates_router(self):
        """Test that decorator creates working router"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        mock_llm = MockLLM('researcher')

        @llm_router(routing_options, llm=mock_llm)
        def test_router(memory) -> Literal['researcher', 'analyst']:
            pass

        assert callable(test_router)
        # Test would require actual execution which needs async setup


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_missing_required_config(self):
        """Test error when required config is missing"""
        with pytest.raises(ValueError, match="requires 'routing_options'"):
            create_llm_router('smart')

        with pytest.raises(ValueError, match="requires 'task_categories'"):
            create_llm_router('task_classifier')

        with pytest.raises(ValueError, match="requires 'routing_logic'"):
            create_llm_router('conversation_analysis')

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, mock_memory):
        """Test fallback when LLM fails completely"""
        routing_options = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

        # Mock LLM that raises exception
        mock_llm = Mock()
        mock_llm.generate = AsyncMock(side_effect=Exception('LLM Error'))

        router = SmartRouter(
            routing_options, llm=mock_llm, max_retries=1, fallback_strategy='first'
        )

        result = await router.route(mock_memory)

        assert result == 'researcher'  # Should fallback to first option

    def test_fallback_strategies(self, mock_memory):
        """Test different fallback strategies"""
        routing_options = {
            'researcher': 'Research tasks',
            'analyst': 'Analysis tasks',
            'writer': 'Writing tasks',
        }

        # Test "first" strategy
        mock_llm = MockLLM('invalid_response')  # Will trigger fallback
        router_first = SmartRouter(
            routing_options, fallback_strategy='first', llm=mock_llm
        )
        assert router_first.get_fallback_route(routing_options) == 'researcher'

        # Test "last" strategy
        router_last = SmartRouter(
            routing_options, fallback_strategy='last', llm=mock_llm
        )
        assert router_last.get_fallback_route(routing_options) == 'writer'

        # Test "random" strategy
        router_random = SmartRouter(
            routing_options, fallback_strategy='random', llm=mock_llm
        )
        fallback = router_random.get_fallback_route(routing_options)
        assert fallback in routing_options.keys()


if __name__ == '__main__':
    pytest.main([__file__])
