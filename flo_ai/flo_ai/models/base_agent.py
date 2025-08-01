from typing import Dict, Any, List, Tuple
from abc import ABC, abstractmethod
from enum import Enum
from flo_ai.llm.base_llm import BaseLLM


class AgentType(Enum):
    CONVERSATIONAL = 'conversational'
    TOOL_USING = 'tool_using'


class ReasoningPattern(Enum):
    DIRECT = 'direct'  # Direct response without explicit reasoning
    REACT = 'react'  # Thought-Action-Observation cycle
    COT = 'cot'  # Chain of Thought reasoning


class BaseAgent(ABC):
    def __init__(
        self,
        name: str,
        system_prompt: str,
        agent_type: AgentType,
        llm: BaseLLM,
        max_retries: int = 3,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.agent_type = agent_type
        self.llm = llm
        self.max_retries = max_retries
        self.resolved_variables = False
        self.conversation_history: List[Dict[str, str]] = []

    @abstractmethod
    async def run(self, input_text: str) -> str:
        """Execute the agent's main functionality"""
        pass

    async def handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        error_prompt = (
            f'An error occurred while processing the request: {str(error)}\n'
            f'Context: {context}\n'
            'Please analyze the error and suggest a correction. '
            'If the error is not recoverable, explain why.'
        )

        try:
            messages = [
                {
                    'role': 'system',
                    'content': 'You are an AI error analysis assistant. '
                    'Analyze errors and suggest corrections when possible.',
                },
                {'role': 'user', 'content': error_prompt},
            ]

            response = await self.llm.generate(messages)
            analysis = self.llm.get_message_content(response)
            should_retry = 'not recoverable' not in analysis.lower()
            return should_retry, analysis

        except Exception as e:
            return False, f'Error during error handling: {str(e)}'

    def add_to_history(self, role: str, content: str, **kwargs):
        """Add a message to conversation history"""
        message = {'role': role, 'content': content}
        message.update(kwargs)  # Add any additional fields like name
        self.conversation_history.append(message)

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
