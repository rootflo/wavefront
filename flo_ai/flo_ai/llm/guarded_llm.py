"""A ``BaseLLM`` decorator that enforces guardrail policy around inference."""

from __future__ import annotations

import asyncio
import contextvars
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from flo_ai.guardrails.contracts import (
    PolicyAction,
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

#: Developer-authored, and appended *after* the user turn by
#: ``Agent._setup_system_message`` — so it cannot be used to find where the
#: model last spoke, and has to be skipped when looking.
SYSTEM_ROLES = frozenset({'system', 'developer'})

#: Stands in for history that the policy would refuse to send now.
#:
#: Substituted rather than dropped: removing a message renumbers the payload
#: and can orphan a tool result from the assistant turn that called it, which
#: providers reject outright. Substituting keeps the shape and sends nothing
#: the policy objects to.
WITHHELD_PLACEHOLDER = '[earlier message withheld by content safety policy]'

#: Ceiling on how many checks one payload runs at once.
#:
#: The checks for a payload run concurrently, because running them in sequence
#: made the wait for a long history the sum of every check: twenty messages
#: against a network adapter is twenty round trips before the model is even
#: called. Concurrency makes it roughly one.
#:
#: Bounded rather than unleashed, because a cold cache on a long history would
#: otherwise fan out one burst per request wide enough to trip a provider's
#: rate limit — and a 429 arrives as an adapter error, which is precisely what
#: the fail-open and fail-closed paths then have to absorb.
MAX_CONCURRENT_CHECKS = 8

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

    def __init__(
        self,
        message: str,
        decision: Optional[PolicyDecision] = None,
        message_index: Optional[int] = None,
    ):
        super().__init__(message)
        self.decision = decision
        self.reasons = list(decision.block_reasons()) if decision else []
        #: Where in the payload the blocking content sat, when a payload was
        #: what got blocked. Lets a caller discard exactly the message that was
        #: refused instead of guessing, which is what keeps a blocked message
        #: out of the conversation it was never allowed to join.
        self.message_index = message_index


class GuardedLLM(BaseLLM):
    """Wraps any ``BaseLLM``, evaluating policy before and after inference.

    The principal is bound here rather than passed per call
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
                logger.warning(
                    f'Guardrail blocked model response '
                    f'[agent={self._principal.agent_id or "-"}] '
                    f'{decision.operator_summary()}'
                )
                raise GuardrailBlocked(decision.caller_message('response'), decision)
            if decision.transformed:
                # Rewrite via get_message_content instead of mutating the raw
                # provider response, whose shape differs per provider.
                _output_redaction.set((response, decision.transformed_content))
                logger.info(
                    f'Guardrail rewrote model response '
                    f'({len(text)} -> {len(decision.transformed_content)} chars) '
                    f'before returning to caller'
                )

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
                logger.warning(
                    f'Guardrail blocked streamed response '
                    f'[agent={self._principal.agent_id or "-"}] '
                    f'{decision.operator_summary()}'
                )
                raise GuardrailBlocked(decision.caller_message('response'), decision)
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

        Every message in an untrusted role is checked, wherever it sits in the
        payload — not only the ones added since the last model call. The
        narrower rule is tempting, and for injection detection it is even the
        right one: a tool result is where an indirect injection arrives, and
        earlier turns were checked when they were new. It does not hold for
        redaction. A TRANSFORM is applied to the copy sent to the provider and
        deliberately not written back (see ``_replace_text``), so the original
        text is still in the caller's ``conversation_history`` on the next
        turn. A scan that stopped at the previous assistant turn never looked
        at it again, and the provider received turn 1's raw PII on every later
        turn — and on every iteration of a tool-calling loop within a single
        turn, since ``Agent._run_with_tools`` re-sends one growing list. The
        guarantee worth having is about the payload leaving the process, which
        means the whole payload.

        Position therefore never terminates the scan, which also settles a
        problem the old boundary had: ``Agent._setup_system_message`` appends
        the system prompt *after* the user turn, so treating a non-untrusted
        role as the boundary stopped the scan before it had evaluated
        anything.

        What the scan does *not* decide is who may refuse the turn. Letting
        the whole payload block meant one refused message ended the
        conversation for good — it stayed in the caller's history, was
        re-scanned on every later turn, and killed each one before the new
        message was read. Refusal is therefore limited to
        ``_blockable_indices``: the user turn just submitted, and tool output
        produced since the model last spoke. Anything else that would block is
        withheld from the payload instead of refusing the request.

        Redaction stays payload-wide, because that is the guarantee the
        payload-wide scan exists for.

        Multimodal messages are checked and rewritten one text block at a
        time, so a redaction lands on the block it came from and the image,
        document and audio blocks beside it survive. See ``_scannable_text``.

        Evaluating the same message on a later turn costs nothing extra: the
        engine caches a verdict per content and policy, so the provider is
        asked once however often the conversation re-sends the message.
        """
        targets = self._scannable_text(messages)
        if not targets:
            return messages

        # One check per *distinct* text, run concurrently under a ceiling. See
        # MAX_CONCURRENT_CHECKS for why it is neither serial nor unbounded.
        #
        # Deduplicated first, because the gather starts every check at the same
        # instant: two identical texts would both find the engine's cache empty
        # and both bill the provider. A sequential scan had this for free, the
        # first check having populated the cache before the second looked. A
        # payload repeats itself more often than it looks - a tool result
        # returned twice, a retried turn, the same block twice in a history.
        distinct = list(dict.fromkeys(text for _, _, text in targets))

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

        async def check(text: str) -> PolicyDecision:
            async with semaphore:
                return await self._engine.evaluate(
                    text,
                    principal=self._principal,
                    stage=WorkflowStage.BEFORE_MODEL,
                    destination='llm_provider',
                )

        verdicts: Dict[str, PolicyDecision] = dict(
            zip(distinct, await asyncio.gather(*(check(text) for text in distinct)))
        )

        # Only content the model has not already answered may refuse the turn.
        #
        # The scan deliberately covers the whole payload, for the redaction
        # reason above. Letting the *whole* payload refuse it as well is what
        # turned one blocked message into a conversation that could never
        # continue: a block leaves the message sitting in the caller's history,
        # every later turn re-scanned it, and every later turn died on it
        # before the new message was even considered. One refusal bricked the
        # thread permanently.
        #
        # Older content that would block now is withheld from the payload
        # instead. It is not sent — the policy is still honoured — but it
        # cannot veto a message the user has just typed. What reaches here is
        # a message refused on an earlier turn and still in the caller's
        # history, or one a since-tightened policy would now refuse; refusing
        # this turn undoes neither.
        blockable = self._blockable_indices(messages)

        # Every block is resolved before anything is applied, and the payload
        # order decides which one is reported. Concurrency means the whole
        # payload is checked even when an early message blocks - one extra
        # round of checks on a request that was going to be refused, in
        # exchange for not waiting out the payload one message at a time.
        for index, _, text in targets:
            decision = verdicts[text]
            if decision.blocked and index in blockable:
                # Operator detail to the log, a safe summary to the caller.
                logger.warning(
                    f'Guardrail blocked request to provider '
                    f'[agent={self._principal.agent_id or "-"}] '
                    f'{decision.operator_summary()}'
                )
                raise GuardrailBlocked(
                    decision.caller_message('request'), decision, message_index=index
                )

        result = list(messages)
        for index, block, text in targets:
            decision = verdicts[text]
            if decision.blocked:
                # Necessarily not blockable; the loop above raised on anything
                # that was.
                result[index] = self._replace_text(
                    result[index], block, WITHHELD_PLACEHOLDER
                )
                # WARNING rather than INFO: reaching this means blocked content
                # is sitting in a stored conversation, which is worth someone
                # looking at even though the request itself is fine.
                logger.warning(
                    f'Guardrail withheld message {index} from the payload '
                    f'(role={messages[index].get("role")}, already answered in '
                    f'an earlier turn) [agent={self._principal.agent_id or "-"}] '
                    f'{decision.operator_summary()}'
                )
            elif decision.transformed:
                # Applied to result[index], not to messages[index]: a message
                # with several text blocks is rewritten once per block, and
                # each rewrite has to land on the previous one's output.
                result[index] = self._replace_text(
                    result[index], block, decision.transformed_content
                )
                # The engine reports its verdict; this reports that the verdict
                # was actually applied to the payload leaving the process. Both
                # are needed - a TRANSFORM the caller silently discards is
                # exactly the bug this makes visible.
                logger.info(
                    f'Guardrail rewrote message {index} '
                    f'(role={messages[index].get("role")}, '
                    f'{len(text)} -> {len(decision.transformed_content)} chars) '
                    f'before sending to provider'
                )
            elif (
                decision.observed_action is PolicyAction.TRANSFORM
                and not decision.enforced
            ):
                # Easy to misread as a broken redaction, so name it.
                logger.info(
                    f'Guardrail found PII in message {index} but the policy is '
                    f'in MONITOR mode, so the provider receives the original '
                    f'text. Switch to ENFORCE to redact.'
                )
        return result

    @staticmethod
    def _blockable_indices(messages: List[Dict[str, Any]]) -> frozenset:
        """Positions whose content may refuse the turn.

        Two things are genuinely new on any given call: the user turn that was
        just submitted, and any tool output produced since the model last
        spoke. Everything else was sent in an earlier request and has already
        been ruled on, whatever the ruling was.

        The obvious rule — everything after the model last spoke — is wrong,
        and wrong in exactly the case this exists to fix. A refused turn
        produces no assistant message, because the call raises instead of
        answering. So a blocked message is never followed by a model turn, and
        a positional boundary leaves it inside the "new" window forever: it
        refuses turn after turn while the boundary stays where it was. That is
        the bug, not a variation on it.

        Taking the *last* user message instead is what makes it terminate. A
        chat turn contributes one new user message; the refused one from last
        turn is no longer the last, so it can no longer veto anything. Tool
        results are matched by role rather than by position, because several
        can arrive together and each is a place an indirect injection lands.

        A payload carrying several new user messages at once has only its last
        one able to block. The rest are withheld rather than refused — still
        not sent, just not grounds for rejecting the request.
        """
        blockable = set()

        # The turn just submitted.
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get('role') == 'user':
                blockable.add(index)
                break

        # Tool output since the model last spoke. System messages are skipped
        # rather than ending the run: Agent._setup_system_message appends the
        # system prompt *after* the user turn, so treating it as the marker
        # would stop the walk before it had seen anything.
        for index in range(len(messages) - 1, -1, -1):
            role = messages[index].get('role')
            if role in SYSTEM_ROLES:
                continue
            if role in UNTRUSTED_ROLES:
                if role != 'user':
                    blockable.add(index)
                continue
            break

        return frozenset(blockable)

    @staticmethod
    def _scannable_text(
        messages: List[Dict[str, Any]],
    ) -> List[Tuple[int, Optional[int], str]]:
        """Every piece of untrusted text in the payload, addressably.

        Returns ``(message index, block index or None, text)``. A string
        ``content`` is one piece addressed by ``None``; a multimodal
        ``content`` list contributes one piece per text block, addressed by
        its position.

        Text blocks are listed separately rather than joined into one string
        because a redaction has to be written back exactly where it came
        from. Joining them produced a single string that no longer
        corresponded to any one block, and assigning it back over the list
        deleted every image, document and audio block in the message — the
        vision model then received text only, and providers that validate
        their content blocks rejected the request outright.
        """
        targets: List[Tuple[int, Optional[int], str]] = []
        for index, message in enumerate(messages):
            if message.get('role') not in UNTRUSTED_ROLES:
                continue
            content = message.get('content')
            if isinstance(content, str):
                if content:
                    targets.append((index, None, content))
            elif isinstance(content, list):
                for position, block in enumerate(content):
                    if not isinstance(block, dict) or block.get('type') != 'text':
                        continue
                    text = block.get('text')
                    if isinstance(text, str) and text:
                        targets.append((index, position, text))
        return targets

    @staticmethod
    def _replace_text(
        message: Dict[str, Any], block: Optional[int], text: Any
    ) -> Dict[str, Any]:
        """``message`` with one piece of its text replaced, as a copy.

        Copy rather than mutate: the caller's list is the agent's conversation
        history, and redacting it in place rewrites the transcript the user
        sees. Leaving it alone is what makes the payload-wide scan above
        necessary.

        For a multimodal message the list and the one block being rewritten
        are copied, and every other block is carried over by reference — so
        images and documents survive untouched without their payloads being
        duplicated.
        """
        replaced = dict(message)
        if block is None:
            replaced['content'] = text
            return replaced

        blocks = list(message.get('content') or ())
        rewritten = dict(blocks[block])
        rewritten['text'] = text
        blocks[block] = rewritten
        replaced['content'] = blocks
        return replaced

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        if isinstance(chunk, dict):
            value = chunk.get('content')
            return value if isinstance(value, str) else ''
        return chunk if isinstance(chunk, str) else ''
