import asyncio
from typing import Dict, Any, List, Tuple, cast, Optional
from abc import ABC, abstractmethod
from enum import Enum
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models.chat_message import (
    AssistantMessage,
    BaseMessage,
    MediaMessageContent,
    TextMessageContent,
    FunctionMessage,
)
from flo_ai.utils.variable_extractor import resolve_variables
from flo_ai.utils.profiler import aprofile


# How an error analysis says that retrying will not help.
NOT_RECOVERABLE_PHRASES = (
    'not recoverable',
    'non-recoverable',
    'unrecoverable',
    'cannot be recovered',
)


class AgentType(Enum):
    CONVERSATIONAL = 'conversational'
    TOOL_USING = 'tool_using'


class ReasoningPattern(Enum):
    DIRECT = 'direct'  # Direct response without explicit reasoning
    REACT = 'react'  # Thought-Action-Observation cycle
    COT = 'cot'  # Chain of Thought reasoning
    PLAN_EXECUTE = 'plan_execute'  # Write a plan, then work through it


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
        # The prompt as written, kept so that a later run with other variables
        # resolves from it and not from the text an earlier run filled in.
        self._prompt_template = system_prompt
        self._resolved_prompt = system_prompt
        self._resolved_with: Dict[str, Any] = {}

    def prompt_template(self) -> str:
        """The system prompt as written, before variables were filled in"""
        # A prompt assigned from outside since it was last resolved is a new
        # template, not a stale resolution.
        if self.system_prompt != self._resolved_prompt:
            self._prompt_template = self.system_prompt
            self._resolved_prompt = self.system_prompt
        return self._prompt_template

    def resolve_system_prompt(self, variables: Dict[str, Any]) -> None:
        """Fill the prompt template's variables in, replacing any earlier values"""
        self.system_prompt = resolve_variables(self.prompt_template(), variables)
        self._resolved_prompt = self.system_prompt

    @abstractmethod
    async def run(self, input_text: str) -> List[BaseMessage]:
        """Execute the agent's main functionality"""
        pass

    async def handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        # Errors that declare themselves final skip LLM analysis entirely.
        # Two reasons: retrying a policy decision only re-derives the same
        # verdict at the cost of another provider call, and the prompt below
        # embeds `context` — which carries the full conversation history — so
        # analysing a guardrail block would send the very content that was
        # just blocked to the model.
        if getattr(error, 'retryable', True) is False:
            return False, str(error)

        error_prompt = (
            f'An error occurred while processing the request: {str(error)}\n'
            f'Context: {context}\n'
            'Please analyze the error and suggest a correction. '
            'If the error is not recoverable, say "not recoverable" and explain why.'
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
            verdict = analysis.lower()
            should_retry = not any(
                phrase in verdict for phrase in NOT_RECOVERABLE_PHRASES
            )
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
                    self.llm.format_function_result_message(
                        input.name, input.content, input.tool_call_id
                    )
                )
            elif isinstance(input, AssistantMessage) and input.tool_calls:
                # A call is only sent with its result. One left unanswered (a
                # run cut short after the call was stored) would make the
                # provider reject the whole request, so only its text is kept.
                following = (
                    self.conversation_history[idx + 1]
                    if idx + 1 < len(self.conversation_history)
                    else None
                )
                text = str(input.content or '')
                formatted = (
                    self.llm.format_tool_call_message(text, input.tool_calls)
                    if isinstance(following, FunctionMessage)
                    else None
                )
                if formatted is not None:
                    message_history.append(formatted)
                elif text:
                    message_history.append({'role': input.role, 'content': text})
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
