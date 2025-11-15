from typing import Dict, Any, List, Optional, Tuple
from abc import ABC, abstractmethod
from enum import Enum
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models.chat_message import (
    BaseMessage,
    MediaMessageContent,
    TextMessageContent,
    FunctionMessage,
)
from flo_ai.utils.variable_extractor import resolve_variables


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
        max_tool_calls: int = 5,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.agent_type = agent_type
        self.llm = llm
        self.max_retries = max_retries
        self.max_tool_calls = max_tool_calls
        self.resolved_variables = False
        self.conversation_history: List[BaseMessage] = []

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

    def add_to_history(self, input_message: BaseMessage | List[BaseMessage]):
        if isinstance(input_message, list):
            self.conversation_history.extend(input_message)
        else:
            self.conversation_history.append(input_message)

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []

    async def _get_message_history(self, variables: Optional[Dict[str, Any]] = None):
        message_history = []
        for input in self.conversation_history:
            # Handle FunctionMessage (OpenAI function role format)
            if isinstance(input, FunctionMessage):
                message_history.append(
                    {'role': input.role, 'name': input.name, 'content': input.content}
                )
            # CRITICAL: Check content type FIRST, before message type
            # This ensures TextMessageContent objects are converted to strings
            elif isinstance(input.content, TextMessageContent):
                resolved_content = resolve_variables(input.content.text, variables)
                message_history.append(
                    {'role': input.role, 'content': resolved_content}
                )
            elif isinstance(input.content, MediaMessageContent):
                if input.content.type == 'image':
                    # Format image message and add to history
                    formatted_content = self.llm.format_image_in_message(input.content)
                    message_history.append(
                        {'role': input.role, 'content': formatted_content}
                    )

                elif input.content.type == 'document':
                    # Format document message and add to history
                    formatted_content = await self.llm.format_document_in_message(
                        input.content
                    )
                    message_history.append(
                        {'role': input.role, 'content': formatted_content}
                    )
                else:
                    raise ValueError(
                        f'Invalid media message content type: {input.content.type}'
                    )
            elif isinstance(input.content, str):
                # Handle other messages with string content (UserMessage, SystemMessage, etc.)
                resolved_content = resolve_variables(input.content, variables)
                message_history.append(
                    {'role': input.role, 'content': resolved_content}
                )
            else:
                raise ValueError(f'Invalid content type: {type(input.content)}')
        return message_history
