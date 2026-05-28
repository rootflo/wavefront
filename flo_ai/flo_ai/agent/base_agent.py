import asyncio
from typing import Dict, Any, List, Tuple, cast, Optional
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
from flo_ai.utils.profiler import aprofile


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
    async def run(self, input_text: str) -> List[BaseMessage]:
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
            self.conversation_history.extend(cast(List[BaseMessage], input_message))
        else:
            self.conversation_history.append(input_message)

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []

    async def _get_message_history(self, variables: Optional[Dict[str, Any]] = None):
        async with aprofile(f'agent.{self.name}.get_message_history'):
            return await self._get_message_history_impl(variables)

    async def _get_message_history_impl(
        self, variables: Optional[Dict[str, Any]] = None
    ):
        """Build the message list passed to the LLM from the conversation history.

        Document formatting (the expensive step — PDF rasterization or
        extraction) is dispatched concurrently via ``asyncio.gather`` and
        cached on the ``DocumentMessageContent`` instance by the underlying
        LLM, so the same document is formatted at most once per LLM across
        all nodes and retries in a workflow.
        """
        variables = variables if variables is not None else {}

        # First pass: kick off one formatting coroutine per *unique* document
        # instance. If the same DocumentMessageContent is referenced at
        # multiple indices, we share the single in-flight task so we never
        # rasterize it twice concurrently.
        doc_tasks_by_id: Dict[int, 'asyncio.Future[Any]'] = {}
        doc_id_by_idx: Dict[int, int] = {}
        for idx, input in enumerate(self.conversation_history):
            if (
                not isinstance(input, FunctionMessage)
                and isinstance(input.content, MediaMessageContent)
                and input.content.type == 'document'
            ):
                doc_id = id(input.content)
                doc_id_by_idx[idx] = doc_id
                if doc_id not in doc_tasks_by_id:
                    doc_tasks_by_id[doc_id] = asyncio.ensure_future(
                        self.llm.format_document_in_message(input.content)  # type: ignore[arg-type]
                    )

        if doc_tasks_by_id:
            formatted_docs = await asyncio.gather(*doc_tasks_by_id.values())
            formatted_by_doc_id: Dict[int, Any] = dict(
                zip(doc_tasks_by_id.keys(), formatted_docs)
            )
        else:
            formatted_by_doc_id = {}

        # Second pass: assemble the provider-ready message list.
        message_history: List[Dict[str, Any]] = []
        for idx, input in enumerate(self.conversation_history):
            if isinstance(input, FunctionMessage):
                message_history.append(
                    {'role': input.role, 'name': input.name, 'content': input.content}
                )
            elif isinstance(input.content, TextMessageContent):
                resolved_content = resolve_variables(input.content.text, variables)
                message_history.append(
                    {'role': input.role, 'content': resolved_content}
                )
            elif isinstance(input.content, MediaMessageContent):
                if input.content.type == 'image':
                    formatted_content = self.llm.format_image_in_message(input.content)  # type: ignore[arg-type]
                    message_history.append(
                        {'role': input.role, 'content': formatted_content}
                    )
                elif input.content.type == 'document':
                    message_history.append(
                        {
                            'role': input.role,
                            'content': formatted_by_doc_id[doc_id_by_idx[idx]],
                        }
                    )
                else:
                    raise ValueError(
                        f'Invalid media message content type: {input.content.type}'
                    )
            elif isinstance(input.content, str):
                resolved_content = resolve_variables(input.content, variables)
                message_history.append(
                    {'role': input.role, 'content': resolved_content}
                )
            else:
                raise ValueError(f'Invalid content type: {type(input.content)}')
        return message_history
