"""Attaching guardrail enforcement to a built agent.

Shared by every service that builds agents. Kept here rather than as a method
on one of them because a second copy is how the workflow path came to run
unguarded while single-agent inference was protected: the settings page read
"enforcing" for traffic nothing inspected.

What remains here is the agent-shaped part. The LLM-level wrap and the run
scope moved to ``common_module.utils.guardrails`` when chatbots needed them
too, since ``chatbots_module`` cannot depend on this package -- the move keeps
there being exactly one implementation, which is the point the paragraph above
is making. They are re-exported below so the call sites in this module did not
have to change.
"""

from typing import Any, Optional

from common_module.log.logger import logger
from common_module.utils.guardrails import (
    guarded_llm,
    guardrail_llm_decorator,  # noqa: F401  (re-exported for callers here)
    guardrail_run_scope as guardrails,  # noqa: F401  (re-exported)
)


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
    # Checked before anything else so that entry points without the guardrails
    # stack stay silent: warning about an agent's missing LLM would be noise on
    # a path that was never going to guard it.
    if guardrails_engine is None or namespace is None:
        return agent

    if getattr(agent, 'llm', None) is None:
        logger.warning(f'Agent {agent_name} has no LLM to guard')
        return agent

    agent.llm = guarded_llm(agent.llm, guardrails_engine, namespace, agent_name)
    return agent


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
    that. The chat path is guarded and stays correct by never calling this,
    which leaves its streams buffered; see the note on its ``stream``.

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
