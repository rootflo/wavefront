"""Attaching guardrail enforcement to a built agent.

Shared by every service that builds agents. Kept here rather than as a method
on one of them because a second copy is how the workflow path came to run
unguarded while single-agent inference was protected: the settings page read
"enforcing" for traffic nothing inspected.
"""

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id


def apply_guardrails(
    agent: Any,
    guardrails_engine: Any,
    namespace: Optional[str],
    agent_name: str,
) -> Any:
    """Wrap ``agent.llm`` so policy is enforced around every model call.

    Applied after ``build()`` rather than at LLM construction, because an agent
    whose model is declared in its YAML never goes through that path — wrapping
    there would leave those agents unguarded while appearing to work for agents
    with a stored LLM override.

    The principal is bound to the wrapper here, so nothing downstream has to
    remember to pass it.

    Returns the agent either way. A missing engine or namespace means unguarded
    rather than an error: the celery worker and other entry points build agents
    without the guardrails stack, and failing there would take out paths that
    never asked for enforcement.
    """
    if guardrails_engine is None or namespace is None:
        return agent

    try:
        from flo_ai.guardrails import Principal
        from flo_ai.llm.guarded_llm import GuardedLLM
    except ImportError:
        logger.warning(
            'Guardrails requested but flo_ai.guardrails is unavailable; '
            'running unguarded'
        )
        return agent

    if getattr(agent, 'llm', None) is None:
        logger.warning(f'Agent {agent_name} has no LLM to guard')
        return agent

    # Read the type before wrapping. GuardedLLM forwards unknown attributes to
    # the inner LLM, so asking the wrapper about itself afterwards would be
    # forwarded straight through and raise.
    inner_name = type(agent.llm).__name__

    agent.llm = GuardedLLM(
        agent.llm,
        guardrails_engine,
        Principal(namespace=namespace, agent_id=agent_name),
    )
    logger.info(
        f'Guardrails attached to agent {agent_name} '
        f'[ns={namespace}, llm={inner_name}, '
        f'adapters={getattr(guardrails_engine, "registered", ()) or "none"}]'
    )
    return agent


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
        from flo_ai.guardrails import Principal
        from flo_ai.llm.guarded_llm import GuardedLLM
    except ImportError:
        logger.warning(
            'Guardrails requested but flo_ai.guardrails is unavailable; '
            'workflow nodes running unguarded'
        )
        return None

    def decorate(llm: Any, node_name: str) -> Any:
        # The builder only offers LLMs it created, so this should not trigger.
        # It is here because the cost of being wrong is silent: a second
        # wrapper evaluates every payload twice, which bills the safety
        # provider twice per call and logs each decision two times.
        if isinstance(llm, GuardedLLM):
            return llm

        logger.info(
            f'Guardrails attached to workflow node {node_name} '
            f'[ns={namespace}, llm={type(llm).__name__}]'
        )
        return GuardedLLM(
            llm,
            guardrails_engine,
            Principal(namespace=namespace, agent_id=node_name),
        )

    return decorate


@contextmanager
def guardrails() -> Iterator[None]:
    """Bind the current request id as the guardrail run id for this block.

    Reuses the platform's request id rather than minting a separate one, so a
    guardrail decision can be lined up against every other log line for the
    same request. Without this every decision logs ``run=-`` and an audit row
    cannot be traced back to the call that produced it.

    Set around execution rather than around agent construction: the wrapper is
    built once and reused across runs, so binding it at construction would
    stamp every later run with the first run's id.
    """
    try:
        from flo_ai.guardrails.run_context import run_scope
    except ImportError:
        # Same posture as apply_guardrails: no guardrails available is not an
        # error for callers that never asked for them.
        yield
        return

    with run_scope(get_current_request_id()):
        yield


def declare_retract_support(llm: Any) -> bool:
    """Tell a ``GuardedLLM`` that its consumer can withdraw text already shown.

    ``GuardedLLM`` refuses to release a response incrementally unless the call
    site asserts this, and it is right to: incremental release can end in a
    retract, and a consumer that ignores one leaves withdrawn text on screen.
    The wrapper cannot see what is downstream of it, so the assertion has to
    come from something that can.

    Deliberately not a parameter on ``apply_guardrails``. Guardrails are
    attached when the agent is built, which is before anyone knows whether
    this request streams, and the same builder serves the workflow nodes and
    the non-streaming path. Setting it there would grant incremental release
    to every consumer of a guarded LLM, including ones that read chunks as
    ``chunk.get('content')`` and would therefore append a replacement to the
    very text it replaces -- ``chat_inference_service.stream`` does exactly
    that, and is only safe today because the chat path is not yet guarded.

    So this is called by the one consumer that does handle a retract, next to
    where it attaches itself, and the claim it is making is checkable from
    those two lines alone.

    Returns whether anything was declared, which is False for an unguarded
    agent - the ordinary case when no policy applies to the namespace.
    """
    try:
        from flo_ai.llm.guarded_llm import GuardedLLM
    except ImportError:
        return False

    if not isinstance(llm, GuardedLLM):
        return False

    # Reaching past the constructor because the flag has to be set after the
    # agent is built, for the reason above. The tidier home for this is a
    # public setter in flo_ai; until then this is the single place that knows
    # the attribute's name.
    llm._supports_retract = True
    return True
