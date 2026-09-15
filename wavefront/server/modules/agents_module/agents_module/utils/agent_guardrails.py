"""Attaching guardrail enforcement to a built agent.

Shared by every service that builds agents. Kept here rather than as a method
on one of them because a second copy is how the workflow path came to run
unguarded while single-agent inference was protected: the settings page read
"enforcing" for traffic nothing inspected.
"""

from contextlib import contextmanager
from typing import Any, Iterator, Optional

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


@contextmanager
def guardrail_run_scope() -> Iterator[None]:
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
