"""
flo_ai - A flexible agent framework for LLM-powered applications
"""

# Models package - Agent framework components
from .models import (
    Agent,
    AgentError,
    BaseAgent,
    AgentType,
    ReasoningPattern,
    DocumentType,
    DocumentMessage,
)

from .builder.agent_builder import AgentBuilder

# LLM package - Language model integrations
from .llm import BaseLLM, Anthropic, OpenAI, OllamaLLM, Gemini, OpenAIVLLM, ImageMessage

# Tool package - Tool framework components
from .tool import Tool, ToolExecutionError, flo_tool, create_tool_from_function

# Arium package - Workflow and memory components
from .arium import (
    Arium,
    BaseArium,
    create_arium,
    MessageMemory,
    BaseMemory,
    StartNode,
    EndNode,
    Edge,
    AriumBuilder,
    AriumEvent,
    AriumEventType,
    default_event_callback,
)

# Utils package - Utility functions
from .utils import FloUtils

__all__ = [
    # Models
    'Agent',
    'AgentError',
    'BaseAgent',
    'AgentType',
    'ReasoningPattern',
    # Utils
    'FloUtils',
    # LLM
    'BaseLLM',
    'Anthropic',
    'OpenAI',
    'OllamaLLM',
    'Gemini',
    'OpenAIVLLM',
    # LLM DataClass
    'ImageMessage',
    'DocumentType',
    'DocumentMessage',
    # Tools
    'Tool',
    'ToolExecutionError',
    'flo_tool',
    'create_tool_from_function',
    # Arium
    'Arium',
    'BaseArium',
    'create_arium',
    'MessageMemory',
    'BaseMemory',
    'StartNode',
    'EndNode',
    'Edge',
    # Builder
    'AgentBuilder',
    'AriumBuilder',
    # Arium Event system
    'AriumEventType',
    'AriumEvent',
    'default_event_callback',
]

__version__ = '1.0.0'
