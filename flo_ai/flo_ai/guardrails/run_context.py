"""Ambient per-run identity for guardrail evaluations.

``Principal`` is bound when a ``GuardedLLM`` is constructed, but ``run_id``
changes on every inference while the wrapper is reused. A ``ContextVar``
carries it without adding a parameter to ``Agent.run`` and every frame between
it and the LLM call — which is what the first implementation attempted, and
which silently lapsed wherever a call site forgot to forward it.

``ContextVar`` propagates into ``asyncio`` tasks created inside the scope, so
this survives the arium/workflow fan-out.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator, Optional

_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'flo_ai_guardrails_run_id', default=None
)


def get_run_id() -> Optional[str]:
    """The run id for the current task, if one has been set."""
    return _current_run_id.get()


@contextmanager
def run_scope(run_id: Optional[str]) -> Iterator[None]:
    """Bind ``run_id`` for the duration of the block.

    Restores the previous value on exit, so nested scopes and concurrent tasks
    do not leak into one another.
    """
    token = _current_run_id.set(run_id)
    try:
        yield
    finally:
        _current_run_id.reset(token)
