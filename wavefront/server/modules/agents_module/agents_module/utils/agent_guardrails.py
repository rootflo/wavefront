"""Guardrails primitives re-exported for the agents module.

The LLM-level wrapper and run scope live in ``common_module.utils.guardrails``
so both chatbots and agents can depend on them. They are re-exported here so
the agents module call sites do not have to change.
"""

from common_module.utils.guardrails import (
    declare_retract_support,  # noqa: F401
    guardrail_llm_provider,  # noqa: F401  (re-exported for callers here)
    guardrail_run_scope as guardrails,  # noqa: F401  (re-exported)
)
