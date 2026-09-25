"""LLM-level guardrail primitives, shared by every inference path.

Lives here rather than beside the agent helpers because chatbots need the same
LLM-level wrap and ``chatbots_module`` must not depend on ``agents_module``.
The alternative was a second copy, and a second copy is how the workflow path
came to run unguarded while single-agent inference was protected: the settings
page read "enforcing" for traffic nothing inspected.

``flo_ai`` is imported lazily and its absence tolerated, because this module
belongs to ``common_module``, which does not declare a ``flo-ai`` dependency.
The fallback covers exactly that -- a missing package -- and nothing else. It
must never be widened to wrap logic that can fail for other reasons: a typo
inside one of those blocks becomes silent non-enforcement, which is the one
outcome this whole subsystem exists to prevent.
"""

from contextlib import contextmanager
from typing import Any, AsyncIterator, Callable, Iterator, Optional

from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id


def guarded_llm(
    llm: Any,
    guardrails_engine: Any,
    namespace: Optional[str],
    agent_id: str,
    user_id: Optional[str] = None,
) -> Any:
    """Wrap ``llm`` so policy is enforced around every model call.

    The principal is bound to the wrapper here, so nothing downstream has to
    remember to pass it.

    Returns the LLM either way. A missing engine or namespace means unguarded
    rather than an error: the celery worker and other entry points build LLMs
    without the guardrails stack, and failing there would take out paths that
    never asked for enforcement.

    ``user_id`` is audit-only -- it is not part of the verdict cache key, so
    populating it neither fragments the cache nor re-bills the safety provider
    per user. Only pass it where the wrapper is built per request. Binding a
    user to an LLM that is cached and reused would attribute one person's
    traffic to another.
    """
    if guardrails_engine is None or namespace is None:
        return llm

    try:
        from flo_ai.guardrails import Principal
        from flo_ai.llm.guarded_llm import GuardedLLM
    except ImportError:
        logger.warning(
            'Guardrails requested but flo_ai.guardrails is unavailable; '
            'running unguarded'
        )
        return llm

    # Should not trigger for callers that wrap once. It is here because the
    # cost of being wrong is silent: a second wrapper evaluates every payload
    # twice, which bills the safety provider twice per call and logs each
    # decision two times.
    if isinstance(llm, GuardedLLM):
        return llm

    # Read the type before wrapping. GuardedLLM forwards unknown attributes to
    # the inner LLM, so asking the wrapper about itself afterwards would be
    # forwarded straight through and raise.
    inner_name = type(llm).__name__

    wrapped = GuardedLLM(
        llm,
        guardrails_engine,
        Principal(namespace=namespace, agent_id=agent_id, user_id=user_id),
    )
    logger.info(
        f'Guardrails attached to {agent_id} '
        f'[ns={namespace}, llm={inner_name}, '
        f'adapters={getattr(guardrails_engine, "registered", ()) or "none"}]'
    )
    return wrapped


def guardrail_llm_decorator(
    guardrails_engine: Any,
    namespace: Optional[str],
) -> Optional[Callable[[Any, str], Any]]:
    """Build the ``llm_decorator`` hook ``AriumBuilder.from_yaml`` accepts.

    ``apply_guardrails`` can only reach agents the server itself built, which
    in a workflow is just the ``namespace/name`` references. Agents declared
    inline in the workflow YAML, and every router's model, are constructed
    inside the builder — including the template the console pre-fills — and
    called the provider with no policy applied. Handing the builder a
    decorator is what closes that: it wraps each LLM at the moment it is
    created, so coverage no longer depends on how an agent happened to be
    declared.

    Returns None when there is nothing to enforce, which keeps the builder on
    its plain path instead of threading a no-op through every node.
    """
    if guardrails_engine is None or namespace is None:
        return None

    try:
        # Probed here rather than left to ``guarded_llm`` so that an absent
        # flo_ai also takes the plain path, instead of handing the builder a
        # decorator that turns out to wrap nothing.
        import flo_ai.llm.guarded_llm  # noqa: F401
    except ImportError:
        logger.warning(
            'Guardrails requested but flo_ai.guardrails is unavailable; '
            'workflow nodes running unguarded'
        )
        return None

    def decorate(llm: Any, node_name: str) -> Any:
        return guarded_llm(llm, guardrails_engine, namespace, node_name)

    return decorate


@contextmanager
def guardrail_run_scope(run_id: Optional[str] = None) -> Iterator[None]:
    """Bind a guardrail run id for this block, defaulting to the request id.

    Reuses the platform's request id rather than minting a separate one, so a
    guardrail decision can be lined up against every other log line for the
    same request. Without this every decision logs ``run=-`` and an audit row
    cannot be traced back to the call that produced it.

    Set around execution rather than around construction: the wrapper is built
    once and reused across runs, so binding it at construction would stamp
    every later run with the first run's id.

    ``run_id`` is explicit for callers that cannot read the context variable at
    the point it matters. A streamed response is iterated after the endpoint
    has returned, so anything that resolves the id lazily there is reading it
    from whatever context happens to be current by then -- pass it in instead.
    """
    try:
        from flo_ai.guardrails.run_context import run_scope
    except ImportError:
        # Same posture as guarded_llm: no guardrails available is not an error
        # for callers that never asked for them.
        yield
        return

    if run_id is None:
        run_id = get_current_request_id()

    with run_scope(run_id):
        yield


async def run_scoped_stream(
    source: AsyncIterator[Any], run_id: Optional[str] = None
) -> AsyncIterator[Any]:
    """Iterate ``source`` with the run scope bound around each step.

    The scope is entered and left inside a single ``__anext__``, never held
    across a ``yield``, and that is the whole point of this function rather
    than a ``with`` around the caller's ``async for``.

    An async generator has no context of its own: it runs in the context of
    whoever resumes it. Starlette cancels ``StreamingResponse.stream_response``
    on client disconnect while it is parked in ``await send(...)``, which
    leaves the body generator suspended at a ``yield`` and never resumed. It is
    then finalised by asyncio's async-generator hook, which throws
    ``GeneratorExit`` into it from a *new task, and so a new context*. A scope
    spanning that ``yield`` would try to reset its token there and raise
    ``ValueError: Token was created in a different Context`` -- replacing the
    ``GeneratorExit``, missing the disconnect handler that was written to
    catch it, and losing the partial reply that handler exists to save.

    Bound this way, the set and the reset always happen in one resumption by
    one consumer. A cancellation at ``__anext__`` arrives in that same context,
    so the reset succeeds; a ``GeneratorExit`` at the ``yield`` below lands
    outside the scope, so no reset is attempted at all.
    """
    iterator = source.__aiter__()
    while True:
        with guardrail_run_scope(run_id):
            try:
                item = await iterator.__anext__()
            except StopAsyncIteration:
                return
        yield item
