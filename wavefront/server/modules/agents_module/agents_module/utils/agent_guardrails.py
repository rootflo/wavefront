"""Guardrails primitives re-exported for the agents module.

The LLM-level wrapper and run scope live in ``common_module.utils.guardrails``
so both chatbots and agents can depend on them. They are re-exported here so
the agents module call sites do not have to change.
"""

from typing import Any

from common_module.utils.guardrails import (
    guardrail_llm_provider,  # noqa: F401  (re-exported for callers here)
    guardrail_run_scope as guardrails,  # noqa: F401  (re-exported)
)


def declare_retract_support(llm: Any) -> bool:
    """Tell a ``GuardedLLM`` that its consumer can withdraw text already shown.

    ``GuardedLLM`` refuses to release a response incrementally unless the call
    site asserts this, and it is right to: incremental release can end in a
    retract, and a consumer that ignores one leaves withdrawn text on screen.
    The wrapper cannot see what is downstream of it, so the assertion has to
    come from something that can.

    Deliberately not applied during agent construction. Guardrails are
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

    llm.declare_retract_support()
    return True
