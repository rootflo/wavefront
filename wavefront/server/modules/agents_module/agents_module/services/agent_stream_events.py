"""Turning a single agent run into a stream of events.

An agent run is opaque from the outside: ``agent.run()`` returns once, at the
end. The two pieces here open it up without changing how it runs.

``StreamingTapLLM`` wraps the agent's LLM and serves a plain completion from
the provider's stream instead of its blocking call, emitting each delta as it
arrives. ``instrument_tools`` wraps the tool callables so a caller can see
which tool fired and what it returned.

Both are attached to the per-request agent after it is built, which is also
what keeps this composable with guardrails: ``apply_guardrails`` has already
replaced ``agent.llm`` with a ``GuardedLLM`` by then, so the tap wraps the
guarded LLM and policy still runs on every streamed call.
"""

import functools
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from common_module.log.logger import logger
from flo_ai.llm.base_llm import BaseLLM


class AgentEventType:
    """Event names carried in the ``event_type`` field of every frame.

    Deliberately overlapping with the workflow streamer's vocabulary
    (``output``, ``error``) so the console can render both with one component.
    """

    AGENT_STARTED = 'agent_started'
    CONTENT_DELTA = 'content_delta'
    TOOL_CALLED = 'tool_called'
    TOOL_RESULT = 'tool_result'
    TOOL_FAILED = 'tool_failed'
    OUTPUT = 'output'
    ERROR = 'error'


#: Cap on any single free-text field in an event. Tool arguments carry whatever
#: the model passed - a base64 image round-tripped through a tool would
#: otherwise be re-sent down the stream in full.
MAX_EVENT_FIELD_CHARS = 2000

Emit = Callable[[Dict[str, Any]], None]


def make_event(event_type: str, **fields: Any) -> Dict[str, Any]:
    """An event frame with its timestamp filled in."""
    return {'event_type': event_type, 'timestamp': time.time(), **fields}


def truncate_for_event(value: Any, limit: int = MAX_EVENT_FIELD_CHARS) -> str:
    """Render `value` as text bounded to `limit` characters."""
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= limit:
        return text
    return f'{text[:limit]}... [truncated, {len(text)} chars]'


class _StreamedResponse:
    """Stands in for a provider response that was assembled from deltas.

    Only ``StreamingTapLLM.get_message_content`` knows how to read it, which is
    the whole point: the agent asks the LLM to extract the text, and the tap is
    the LLM it is asking.
    """

    __slots__ = ('content',)

    def __init__(self, content: str) -> None:
        self.content = content


class StreamingTapLLM(BaseLLM):
    """Serves completions from the provider's stream, emitting deltas.

    Modelled on ``flo_ai.llm.guarded_llm.GuardedLLM``: a ``BaseLLM`` decorator
    that stays substitutable for the LLM it wraps.

    Only calls that carry neither tools nor an output schema are streamed.
    ``Agent._run_with_tools`` passes ``functions=`` on every iteration of its
    loop, and no provider's ``stream()`` surfaces tool-call deltas - it yields
    text only - so streaming a tool-using call would silently drop the tool
    calls. Those calls are delegated untouched and the run behaves exactly as
    it does without the tap; the same goes for an agent with an output schema,
    whose structured output comes from the provider's non-streaming path.
    """

    def __init__(self, inner_llm: BaseLLM, emit: Emit) -> None:
        # Populate BaseLLM's own attributes from the wrapped instance so the
        # wrapper is substitutable: telemetry reads llm.model, and builders
        # assign llm.temperature.
        super().__init__(
            model=getattr(inner_llm, 'model', ''),
            api_key=getattr(inner_llm, 'api_key', None),
            temperature=getattr(inner_llm, 'temperature', 0.7),
            **getattr(inner_llm, 'kwargs', {}),
        )
        object.__setattr__(self, '_inner_llm', inner_llm)
        self._emit = emit

    # -- transparent delegation ------------------------------------------

    def __getattr__(self, item: str) -> Any:
        """Forward anything not defined here to the wrapped LLM."""
        if item.startswith('_'):
            raise AttributeError(item)
        return getattr(self.__dict__['_inner_llm'], item)

    def __setattr__(self, key: str, value: Any) -> None:
        """Mirror config writes onto the wrapped LLM, as GuardedLLM does."""
        super().__setattr__(key, value)
        if key in ('model', 'api_key', 'temperature'):
            inner = self.__dict__.get('_inner_llm')
            if inner is not None:
                setattr(inner, key, value)

    # -- inference -------------------------------------------------------

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if functions or output_schema:
            return await self._inner_llm.generate(
                messages, functions=functions, output_schema=output_schema
            )

        parts: List[str] = []
        async for chunk in self._inner_llm.stream(messages):
            content = chunk.get('content') if chunk else None
            if not content:
                continue
            parts.append(content)
            self._emit(make_event(AgentEventType.CONTENT_DELTA, content=content))

        return _StreamedResponse(''.join(parts))

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        # Nothing in the agent path calls this - the tap exists because
        # Agent.run() only ever calls generate() - but BaseLLM declares it
        # abstract, and a caller that found the wrapper should get the
        # provider's stream rather than a NotImplementedError.
        extra = dict(kwargs)
        if output_schema is not None:
            extra['output_schema'] = output_schema
        async for chunk in self._inner_llm.stream(messages, functions, **extra):
            yield chunk

    # -- BaseLLM abstract surface ----------------------------------------

    def get_message_content(self, response: Any) -> str:
        if isinstance(response, _StreamedResponse):
            return response.content
        # Delegated, not reimplemented: for a GuardedLLM inner this is also
        # where an AFTER_MODEL redaction is applied.
        return self._inner_llm.get_message_content(response)

    def format_tool_for_llm(self, tool: Any) -> Dict[str, Any]:
        return self._inner_llm.format_tool_for_llm(tool)

    def format_tools_for_llm(self, tools: Any) -> List[Dict[str, Any]]:
        return self._inner_llm.format_tools_for_llm(tools)

    def format_image_in_message(self, image: Any) -> Any:
        return self._inner_llm.format_image_in_message(image)

    async def format_document_in_message(self, document: Any) -> Any:
        # Delegated for the reason GuardedLLM gives: BaseLLM's default
        # rasterizes PDFs and caches under type(self).__name__, which would
        # both bypass the provider's own handling and split the cache.
        return await self._inner_llm.format_document_in_message(document)


def instrument_tools(agent: Any, emit: Emit) -> None:
    """Wrap the agent's tool callables so each call reports itself.

    Mutating the ``Tool`` objects in place is safe because they are built per
    request - ``ToolLoader.load_tool`` constructs a new ``Tool`` on every
    lookup, as do the message-processor and API-service loaders - so no other
    run shares these instances.

    Wrapping ``tool.function`` rather than ``tool.execute`` keeps flo_ai's own
    error handling (``ToolExecutionError``, logging) wrapped around ours
    instead of inside it.
    """
    for tool in getattr(agent, 'tools', None) or []:
        original = tool.function

        def make_wrapper(tool_name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(fn)
            async def wrapper(**kwargs: Any) -> Any:
                emit(
                    make_event(
                        AgentEventType.TOOL_CALLED,
                        tool_name=tool_name,
                        arguments=truncate_for_event(kwargs),
                    )
                )
                started = time.time()
                try:
                    result = await fn(**kwargs)
                except Exception as exc:
                    emit(
                        make_event(
                            AgentEventType.TOOL_FAILED,
                            tool_name=tool_name,
                            error=str(exc),
                            execution_time=time.time() - started,
                        )
                    )
                    raise
                emit(
                    make_event(
                        AgentEventType.TOOL_RESULT,
                        tool_name=tool_name,
                        result=truncate_for_event(result),
                        execution_time=time.time() - started,
                    )
                )
                return result

            return wrapper

        tool.function = make_wrapper(tool.name, original)

    logger.debug(
        f'Instrumented {len(getattr(agent, "tools", None) or [])} tool(s) for streaming'
    )
