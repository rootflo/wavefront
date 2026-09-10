"""A ``BaseLLM`` decorator that enforces guardrail policy around inference."""

from __future__ import annotations

import contextvars
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from flo_ai.guardrails.contracts import (
    PolicyDecision,
    Principal,
    WorkflowStage,
)
from flo_ai.guardrails.engine import GuardrailsEngine
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.logger import logger

#: Roles whose content did not come from us. Assistant turns were already
#: checked on the way out, and the system prompt is developer-authored, so
#: re-scanning them on every turn costs a provider call and finds nothing.
UNTRUSTED_ROLES = frozenset({'user', 'tool', 'function'})

#: Carries the redaction for the response most recently returned by
#: ``generate`` on this task. ``get_message_content`` consults it so an
#: AFTER_MODEL rewrite reaches the caller without this class having to mutate
#: provider-specific response objects, whose shapes differ per provider.
#:
#: Holds the response object itself, not its ``id()``. An id is only unique
#: among *live* objects: once the response is collected CPython reuses the
#: address, and the next allocation compares equal — which surfaced as one
#: call's redacted text being returned for an unrelated later response.
#: Keeping the reference both makes the identity check exact and prevents the
#: address from being recycled. At most one response is pinned per task.
_output_redaction: contextvars.ContextVar[Optional[Tuple[Any, str]]] = (
    contextvars.ContextVar('flo_ai_guardrail_output_redaction', default=None)
)


class GuardrailBlocked(AgentError):
    """Raised when policy blocks a prompt or a response.

    ``retryable`` is False because a policy decision is not a transient
    failure: retrying re-bills the safety provider, re-sends the payload, and
    arrives at the same verdict.
    """

    retryable = False

    def __init__(self, message: str, decision: Optional[PolicyDecision] = None):
        super().__init__(message)
        self.decision = decision
        self.reasons = list(decision.block_reasons()) if decision else []


class GuardedLLM(BaseLLM):
    """Wraps any ``BaseLLM``, evaluating policy before and after inference.

    The principal is bound here rather than passed per call. An earlier
    revision threaded an ``evaluation_context`` keyword from ``Agent.run``
    down to ``generate``; every frame that forgot to forward it silently
    disabled all checks, and the tool-calling path forgot.
    """

    def __init__(
        self,
        inner_llm: BaseLLM,
        engine: GuardrailsEngine,
        principal: Optional[Principal] = None,
    ) -> None:
        # Populate BaseLLM's own attributes from the wrapped instance so the
        # wrapper is substitutable: builders assign llm.temperature, and
        # telemetry reads llm.model.
        super().__init__(
            model=getattr(inner_llm, 'model', ''),
            api_key=getattr(inner_llm, 'api_key', None),
            temperature=getattr(inner_llm, 'temperature', 0.7),
            **getattr(inner_llm, 'kwargs', {}),
        )
        object.__setattr__(self, '_inner_llm', inner_llm)
        self._engine = engine
        self._principal = principal or Principal()

    # -- transparent delegation ------------------------------------------

    def __getattr__(self, item: str) -> Any:
        """Forward anything not defined here to the wrapped LLM.

        Hand-written proxies drift from ``BaseLLM`` as it grows; this keeps
        provider-specific helpers reachable through the wrapper.
        """
        if item.startswith('_'):
            raise AttributeError(item)
        return getattr(self.__dict__['_inner_llm'], item)

    def __setattr__(self, key: str, value: Any) -> None:
        """Mirror config writes onto the wrapped LLM.

        ``AgentBuilder`` does ``self._llm.temperature = ...`` after
        construction. Without this the value would sit on the wrapper and the
        real client would keep its default.
        """
        super().__setattr__(key, value)
        if key in ('model', 'api_key', 'temperature'):
            inner = self.__dict__.get('_inner_llm')
            if inner is not None:
                setattr(inner, key, value)

    # -- BaseLLM abstract surface ----------------------------------------

    def get_message_content(self, response: Any) -> str:
        redaction = _output_redaction.get()
        if redaction is not None and redaction[0] is response:
            return redaction[1]
        return self._inner_llm.get_message_content(response)

    def format_tool_for_llm(self, tool: Any) -> Dict[str, Any]:
        return self._inner_llm.format_tool_for_llm(tool)

    def format_tools_for_llm(self, tools: Any) -> List[Dict[str, Any]]:
        return self._inner_llm.format_tools_for_llm(tools)

    def format_image_in_message(self, image: Any) -> Any:
        return self._inner_llm.format_image_in_message(image)

    async def format_document_in_message(self, document: Any) -> Any:
        # Delegated rather than inherited: BaseLLM's default rasterises PDFs
        # and caches under type(self).__name__, so inheriting it would bypass
        # the provider's native document handling and cache under 'GuardedLLM'.
        return await self._inner_llm.format_document_in_message(document)

    # -- inference -------------------------------------------------------

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        messages = await self._guard_input(messages)

        response = await self._inner_llm.generate(
            messages, functions=functions, output_schema=output_schema
        )

        text = self._inner_llm.get_message_content(response)
        if text:
            decision = await self._engine.evaluate(
                text,
                principal=self._principal,
                stage=WorkflowStage.AFTER_MODEL,
                destination='user',
            )
            if decision.blocked:
                raise GuardrailBlocked(
                    f'Response blocked by guardrails: '
                    f'{"; ".join(decision.block_reasons())}',
                    decision,
                )
            if decision.transformed:
                # Rewrite via get_message_content instead of mutating the raw
                # provider response, whose shape differs per provider.
                _output_redaction.set((response, decision.transformed_content))

        return response

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        messages = await self._guard_input(messages)

        # No concrete provider's stream() accepts output_schema - they are all
        # (messages, functions=None, **kwargs). Forwarding it unconditionally
        # would make every guarded stream fail where an unguarded one works,
        # so it is only passed through when the caller actually set it.
        extra = dict(kwargs)
        if output_schema is not None:
            extra['output_schema'] = output_schema

        # Streaming and output checks are in tension: a chunk already
        # delivered cannot be recalled. When the policy checks output, the
        # stream is collected and vetted before any of it is released, which
        # keeps the guarantee at the cost of incremental delivery. With no
        # output checks configured, chunks flow straight through.
        if not await self._engine.has_checks(
            self._principal, WorkflowStage.AFTER_MODEL
        ):
            async for chunk in self._inner_llm.stream(messages, functions, **extra):
                yield chunk
            return

        buffered: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        async for chunk in self._inner_llm.stream(messages, functions, **extra):
            buffered.append(chunk)
            part = self._chunk_text(chunk)
            if part:
                text_parts.append(part)

        combined = ''.join(text_parts)
        if combined:
            decision = await self._engine.evaluate(
                combined,
                principal=self._principal,
                stage=WorkflowStage.AFTER_MODEL,
                destination='user',
            )
            if decision.blocked:
                raise GuardrailBlocked(
                    f'Response blocked by guardrails: '
                    f'{"; ".join(decision.block_reasons())}',
                    decision,
                )
            if decision.transformed:
                logger.warning(
                    'Guardrail redacted a streamed response; emitting the '
                    'redacted text as a single chunk'
                )
                yield {'content': decision.transformed_content}
                return

        for chunk in buffered:
            yield chunk

    # -- input checking --------------------------------------------------

    async def _guard_input(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Evaluate untrusted inbound content, returning messages to send.

        Only the trailing run of untrusted messages is checked. In a
        tool-calling loop those are exactly what is new since the previous
        model call — the freshly returned tool results, which is the payload
        an indirect prompt injection arrives in. Earlier turns were checked
        when they were new, so re-scanning them bills the provider again to
        re-derive the same verdict.
        """
        targets = self._trailing_untrusted(messages)
        if not targets:
            return messages

        result = list(messages)
        for index in targets:
            text = self._message_text(messages[index])
            if not text:
                continue
            decision = await self._engine.evaluate(
                text,
                principal=self._principal,
                stage=WorkflowStage.BEFORE_MODEL,
                destination='llm_provider',
            )
            if decision.blocked:
                raise GuardrailBlocked(
                    f'Request blocked by guardrails: '
                    f'{"; ".join(decision.block_reasons())}',
                    decision,
                )
            if decision.transformed:
                # Copy rather than mutate: the caller's list is the agent's
                # conversation history, and redacting it in place rewrites
                # the transcript the user sees.
                redacted = dict(messages[index])
                redacted['content'] = decision.transformed_content
                result[index] = redacted
        return result

    @staticmethod
    def _trailing_untrusted(messages: List[Dict[str, Any]]) -> List[int]:
        indices: List[int] = []
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get('role') in UNTRUSTED_ROLES:
                indices.append(index)
            else:
                break
        return list(reversed(indices))

    @staticmethod
    def _message_text(message: Dict[str, Any]) -> Optional[str]:
        """Extract scannable text, including from multimodal content blocks."""
        content = message.get('content')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block.get('text', '')
                for block in content
                if isinstance(block, dict) and block.get('type') == 'text'
            ]
            return '\n'.join(p for p in parts if p) or None
        return None

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        if isinstance(chunk, dict):
            value = chunk.get('content')
            return value if isinstance(value, str) else ''
        return chunk if isinstance(chunk, str) else ''
